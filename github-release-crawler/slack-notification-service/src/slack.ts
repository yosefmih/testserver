import { WebClient, KnownBlock } from '@slack/web-api';
import { createTracedOperation } from './telemetry';
import { SlackIntegration, AnalysisResult } from './database';

export class SlackNotifier {
  private clients: Map<string, WebClient> = new Map();

  constructor() {
    console.log('🔧 Slack Notifier initialized');
  }

  private getClient(botToken: string): WebClient {
    if (!this.clients.has(botToken)) {
      const client = new WebClient(botToken);
      this.clients.set(botToken, client);
      console.log('📱 New Slack client created');
    }
    return this.clients.get(botToken)!;
  }

  async testConnection(integration: SlackIntegration): Promise<boolean> {
    return createTracedOperation('slack.testConnection', async () => {
      try {
        const client = this.getClient(integration.bot_token);
        const result = await client.auth.test();
        
        if (result.ok) {
          console.log('✅ Slack connection test successful:', result.team);
          return true;
        } else {
          console.log('❌ Slack connection test failed:', result.error);
          return false;
        }
      } catch (error) {
        console.error('❌ Slack connection test error:', error);
        return false;
      }
    }, {
      'slack.workspace_id': integration.workspace_id,
      'slack.workspace_name': integration.workspace_name
    });
  }

  async sendAnalysisNotification(
    integration: SlackIntegration,
    analysisResult: AnalysisResult,
    channel: string = integration.default_channel
  ): Promise<{ success: boolean; messageTs?: string; error?: string }> {
    return createTracedOperation('slack.sendAnalysisNotification', async () => {
      try {
        const client = this.getClient(integration.bot_token);
        
        const message = this.formatAnalysisMessage(analysisResult);
        
        console.log(`📤 Sending Slack notification to ${channel}`);
        
        const result = await client.chat.postMessage({
          channel: channel,
          ...message,
          username: 'GitHub Release Analyzer',
          icon_emoji: ':github:',
          link_names: true
        });

        if (result.ok && result.ts) {
          console.log('✅ Slack message sent successfully:', result.ts);
          return { success: true, messageTs: result.ts };
        } else {
          console.error('❌ Slack message failed:', result.error);
          return { success: false, error: result.error };
        }
      } catch (error) {
        console.error('❌ Slack notification error:', error);
        return { success: false, error: (error as Error).message };
      }
    }, {
      'slack.workspace_id': integration.workspace_id,
      'slack.channel': channel,
      'analysis.repository': analysisResult.repository_url,
      'analysis.severity': analysisResult.severity,
      'analysis.trace_id': analysisResult.trace_id
    });
  }

  private formatAnalysisMessage(analysis: AnalysisResult) {
    const severityEmoji = {
      low: '🟢',
      medium: '🟡',
      high: '🟠',
      critical: '🔴'
    };

    const emoji = severityEmoji[analysis.severity];
    const repoName = analysis.repository_url.split('/').slice(-2).join('/');
    
    const blocks: KnownBlock[] = [
      {
        type: "header",
        text: {
          type: "plain_text",
          text: `${emoji} GitHub Release Analysis Complete`
        }
      },
      {
        type: "section",
        fields: [
          {
            type: "mrkdwn",
            text: `*Repository:*\n<${analysis.repository_url}|${repoName}>`
          },
          {
            type: "mrkdwn",
            text: `*Version:*\n${analysis.from_version || 'Latest'} → ${analysis.to_version}`
          },
          {
            type: "mrkdwn",
            text: `*Severity:*\n${emoji} ${analysis.severity.toUpperCase()}`
          },
          {
            type: "mrkdwn",
            text: `*Status:*\n${analysis.status}`
          }
        ]
      }
    ];

    if (analysis.analysis_summary) {
      blocks.push({
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*Analysis Summary:*\n${analysis.analysis_summary}`
        }
      });
    }

    if (analysis.breaking_changes && Object.keys(analysis.breaking_changes).length > 0) {
      const breakingChangesText = this.formatBreakingChanges(analysis.breaking_changes);
      blocks.push({
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*Breaking Changes:*\n${breakingChangesText}`
        }
      });
    }

    // Add footer with trace ID for debugging
    blocks.push({
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: `Trace ID: \`${analysis.trace_id}\` | Generated at ${new Date().toISOString()}`
        }
      ]
    });

    return {
      blocks,
      text: `${emoji} GitHub Release Analysis: ${repoName} ${analysis.to_version} - ${analysis.severity} severity`
    };
  }

  private formatBreakingChanges(breakingChanges: any): string {
    if (typeof breakingChanges === 'string') {
      return breakingChanges;
    }

    if (typeof breakingChanges === 'object') {
      const changes = [];
      
      if (breakingChanges.summary) {
        changes.push(breakingChanges.summary);
      }
      
      if (breakingChanges.changes && Array.isArray(breakingChanges.changes)) {
        const changesList = breakingChanges.changes
          .slice(0, 5) // Limit to first 5 changes
          .map((change: any) => `• ${change.description || change}`)
          .join('\n');
        changes.push(changesList);
        
        if (breakingChanges.changes.length > 5) {
          changes.push(`... and ${breakingChanges.changes.length - 5} more changes`);
        }
      }

      return changes.join('\n\n');
    }

    return JSON.stringify(breakingChanges, null, 2);
  }

  async sendTestMessage(integration: SlackIntegration, channel: string): Promise<{ success: boolean; messageTs?: string; error?: string }> {
    return createTracedOperation('slack.sendTestMessage', async () => {
      try {
        const client = this.getClient(integration.bot_token);
        
        const result = await client.chat.postMessage({
          channel: channel,
          text: '🧪 Test message from GitHub Release Analyzer',
          blocks: [
            {
              type: "section",
              text: {
                type: "mrkdwn",
                text: "🧪 *Test Message*\n\nThis is a test message to verify the Slack integration is working correctly."
              }
            },
            {
              type: "context",
              elements: [
                {
                  type: "mrkdwn",
                  text: `Sent at ${new Date().toISOString()}`
                }
              ]
            }
          ]
        });

        if (result.ok && result.ts) {
          return { success: true, messageTs: result.ts };
        } else {
          return { success: false, error: result.error };
        }
      } catch (error) {
        return { success: false, error: (error as Error).message };
      }
    }, {
      'slack.workspace_id': integration.workspace_id,
      'slack.channel': channel,
      'slack.test': true
    });
  }
}