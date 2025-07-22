#!/usr/bin/env node

import { Command } from 'commander';
import * as dotenv from 'dotenv';
import { BreakingChangesAnalyzer } from './analyzer';
import { initializeTelemetry } from './telemetry';

dotenv.config();

initializeTelemetry();

const program = new Command();

program
  .name('github-release-crawler')
  .description('Analyze GitHub repository releases for breaking changes using LLMs')
  .version('1.0.0');

program
  .command('analyze')
  .description('Analyze releases for breaking changes')
  .requiredOption('-u, --url <url>', 'GitHub repository URL')
  .requiredOption('-c, --current-version <version>', 'Current version to compare against')
  .option('-t, --github-token <token>', 'GitHub API token (optional, uses GITHUB_TOKEN env var)')
  .option('-k, --anthropic-key <key>', 'Anthropic API key (optional, uses ANTHROPIC_API_KEY env var)')
  .option('--json', 'Output results as JSON')
  .action(async (options) => {
    try {
      const githubToken = options.githubToken || process.env.GITHUB_TOKEN;
      const anthropicApiKey = options.anthropicKey || process.env.ANTHROPIC_API_KEY;

      // GitHub token is optional for public repositories
      if (!githubToken) {
        console.log('No GitHub token provided. Rate limits will be lower but should work for public repositories.');
      }

      if (!anthropicApiKey) {
        console.error('Error: Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable or use --anthropic-key option.');
        process.exit(1);
      }

      const analyzer = new BreakingChangesAnalyzer(githubToken, anthropicApiKey);
      
      console.log(`Analyzing releases for ${options.url} after version ${options.currentVersion}...`);
      
      const result = await analyzer.analyze({
        githubUrl: options.url,
        currentVersion: options.currentVersion,
        githubToken,
        anthropicApiKey
      });
      console.log(result);
      if (options.json) {
        console.log(JSON.stringify(result, null, 2));
      } else {
        printAnalysisResult(result);
      }
    } catch (error) {
      console.error('Error in analyze command:', error);
      process.exit(1);
    }
  });

program
  .command('list-releases')
  .description('List all available releases for a repository')
  .requiredOption('-u, --url <url>', 'GitHub repository URL')
  .option('-t, --github-token <token>', 'GitHub API token (optional, uses GITHUB_TOKEN env var)')
  .option('--json', 'Output results as JSON')
  .action(async (options) => {
    try {
      const githubToken = options.githubToken || process.env.GITHUB_TOKEN;
      const analyzer = new BreakingChangesAnalyzer(githubToken);
      
      const releases = await analyzer.getAvailableReleases(options.url);
      
      if (options.json) {
        console.log(JSON.stringify(releases, null, 2));
      } else {
        console.log(`\nAvailable releases for ${options.url}:\n`);
        releases.forEach(release => {
          const prereleaseLabel = release.prerelease ? ' (prerelease)' : '';
          console.log(`${release.version}${prereleaseLabel} - ${new Date(release.publishedAt).toLocaleDateString()}`);
        });
      }
    } catch (error) {
      console.error('Error:', error instanceof Error ? error.message : error);
      process.exit(1);
    }
  });

function printAnalysisResult(result: any): void {
  console.log('\n=== BREAKING CHANGES ANALYSIS ===\n');
  
  console.log(`Risk Level: ${result.riskLevel.toUpperCase()}\n`);
  
  console.log('Summary:');
  console.log(result.summary);
  console.log();

  if (result.breakingChanges.length > 0) {
    console.log('Breaking Changes Found:');
    console.log('=' .repeat(50));
    
    result.breakingChanges.forEach((change: any, index: number) => {
      console.log(`\n${index + 1}. Version ${change.version} - [${change.severity.toUpperCase()}]`);
      console.log(`   Category: ${change.category}`);
      console.log(`   Description: ${change.description}`);
      if (change.mitigation) {
        console.log(`   Mitigation: ${change.mitigation}`);
      }
    });
    console.log();
  } else {
    console.log('✅ No breaking changes found!\n');
  }

  if (result.recommendedActions.length > 0) {
    console.log('Recommended Actions:');
    result.recommendedActions.forEach((action: string, index: number) => {
      console.log(`${index + 1}. ${action}`);
    });
    console.log();
  }
}

program.parse();