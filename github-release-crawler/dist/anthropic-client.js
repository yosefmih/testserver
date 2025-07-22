"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.AnthropicClient = void 0;
const sdk_1 = __importDefault(require("@anthropic-ai/sdk"));
const api_1 = require("@opentelemetry/api");
const tracer = api_1.trace.getTracer('anthropic-client');
class AnthropicClient {
    constructor(apiKey) {
        this.client = new sdk_1.default({
            apiKey,
        });
    }
    async analyzeReleaseNotes(releaseNotes) {
        return tracer.startActiveSpan('anthropic.analyzeReleaseNotes', async (span) => {
            try {
                span.setAttributes({
                    'anthropic.releases.count': releaseNotes.length
                });
                const prompt = this.buildAnalysisPrompt(releaseNotes);
                const response = await this.client.messages.create({
                    model: 'claude-3-5-sonnet-20241022',
                    max_tokens: 4000,
                    messages: [{
                            role: 'user',
                            content: prompt
                        }]
                });
                const analysisText = response.content[0].type === 'text' ? response.content[0].text : '';
                const analysis = this.parseAnalysisResponse(analysisText);
                span.setAttributes({
                    'anthropic.analysis.breakingChanges.count': analysis.breakingChanges.length,
                    'anthropic.analysis.riskLevel': analysis.riskLevel
                });
                return analysis;
            }
            catch (error) {
                span.recordException(error);
                throw error;
            }
            finally {
                span.end();
            }
        });
    }
    buildAnalysisPrompt(releaseNotes) {
        const releaseText = releaseNotes.map(release => `## Version ${release.version} (${release.publishedAt})
${release.notes || 'No release notes provided'}`).join('\n\n');
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
    parseAnalysisResponse(response) {
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
        }
        catch (error) {
            return {
                breakingChanges: [],
                summary: `Analysis failed to parse: ${response}`,
                riskLevel: 'medium',
                recommendedActions: ['Manual review of release notes recommended']
            };
        }
    }
}
exports.AnthropicClient = AnthropicClient;
//# sourceMappingURL=anthropic-client.js.map