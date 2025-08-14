import { trace } from '@opentelemetry/api';
import { observeOpenAI } from 'langfuse';
import OpenAI from 'openai';

const tracer = trace.getTracer(process.env.OTEL_SERVICE_NAME || 'porter');

export interface BreakingChange {
  version: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  description: string;
  category: string;
  mitigation?: string;
}

export interface AnalysisResult {
  breakingChanges: BreakingChange[];
  summary: string;
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
  recommendedActions: string[];
}

export class AnthropicClient {
  private client: OpenAI;

  constructor(apiKey: string) {
    console.log('🔍 Testing Langfuse connectivity...');
    this.testLangfuseConnectivity();

    const openaiClient = new OpenAI({
      apiKey,
      baseURL: 'https://api.anthropic.com/v1/',
    });
    
    // Wrap with Langfuse for automatic tracing with explicit config
    this.client = observeOpenAI(openaiClient, {
      traceName: 'github-release-analysis',
      clientInitParams: {
        secretKey: process.env.LANGFUSE_SECRET_KEY,
        publicKey: process.env.LANGFUSE_PUBLIC_KEY,
        baseUrl: process.env.LANGFUSE_BASE_URL
      }
    });
  }

  private async testLangfuseConnectivity() {
    try {
      const response = await fetch(`${process.env.LANGFUSE_BASE_URL}/api/public/health`);
      console.log('✅ Langfuse health check:', response.status);
    } catch (error) {
      console.error('❌ Langfuse connectivity failed:', error instanceof Error ? error.message : error);
    }
  }

  async analyzeReleaseNotes(releaseNotes: Array<{ version: string; notes: string; publishedAt: string }>): Promise<AnalysisResult> {
    return tracer.startActiveSpan('anthropic.analyzeReleaseNotes', async (span) => {
      try {
        span.setAttributes({
          'anthropic.releases.count': releaseNotes.length
        });

        const prompt = this.buildAnalysisPrompt(releaseNotes);
        
        const response = await this.client.chat.completions.create({
          model: 'claude-3-5-sonnet-20241022',
          max_tokens: 4000,
          messages: [{
            role: 'user',
            content: prompt
          }]
        });

        const analysisText = response.choices[0].message.content || '';
        const analysis = this.parseAnalysisResponse(analysisText);

        // Flush traces to Langfuse
        console.log('🔍 Flushing traces to Langfuse...');
        try {
          await (this.client as any).flushAsync();
          console.log('✅ Traces flushed successfully');
        } catch (flushError) {
          console.error('❌ Flush error:', flushError);
        }

        span.setAttributes({
          'anthropic.analysis.breakingChanges.count': analysis.breakingChanges.length,
          'anthropic.analysis.riskLevel': analysis.riskLevel
        });

        return analysis;
      } catch (error) {
        span.recordException(error as Error);
        throw error;
      } finally {
        span.end();
      }
    });
  }

  private buildAnalysisPrompt(releaseNotes: Array<{ version: string; notes: string; publishedAt: string }>): string {
    const releaseText = releaseNotes.map(release => 
      `## Version ${release.version} (${release.publishedAt})
${release.notes || 'No release notes provided'}`
    ).join('\n\n');

    return `You are a software engineering expert analyzing GitHub release notes to identify breaking changes. 

Analyze the following release notes and identify ALL breaking changes, including:
- API changes (method signatures, parameter changes, removed methods)
- Configuration changes (removed/renamed config options, changed defaults)
- Behavioral changes (different output, changed error handling)
- Dependency requirement changes
- Removed features or deprecations becoming removals
- Schema or data format changes

For each breaking change, provide:
1. Version where it was introduced
2. Severity level (low/medium/high/critical)
3. Clear description of the change
4. Category (API, Configuration, Behavior, Dependencies, Features, Schema, etc.)
5. Suggested mitigation if applicable

Also provide:
- Overall risk level assessment
- Summary of the analysis
- Recommended actions for upgrading

Release Notes:
${releaseText}

Please respond in the following JSON format:
{
  "breakingChanges": [
    {
      "version": "x.y.z",
      "severity": "high",
      "description": "Detailed description of the breaking change",
      "category": "API",
      "mitigation": "Steps to mitigate this change"
    }
  ],
  "summary": "Overall summary of breaking changes found",
  "riskLevel": "medium",
  "recommendedActions": [
    "Action 1",
    "Action 2"
  ]
}`;
  }

  private parseAnalysisResponse(response: string): AnalysisResult {
    try {
      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (!jsonMatch) {
        throw new Error('No JSON found in response');
      }

      const analysis = JSON.parse(jsonMatch[0]);
      
      return {
        breakingChanges: analysis.breakingChanges || [],
        summary: analysis.summary || 'No summary provided',
        riskLevel: analysis.riskLevel || 'medium',
        recommendedActions: analysis.recommendedActions || []
      };
    } catch (error) {
      return {
        breakingChanges: [],
        summary: `Analysis failed to parse: ${response}`,
        riskLevel: 'medium',
        recommendedActions: ['Manual review of release notes recommended']
      };
    }
  }
}