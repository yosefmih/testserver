#!/bin/bash
set -e

echo "=== Worker entrypoint starting ==="
echo "ANTHROPIC_API_KEY set: $([ -n "$ANTHROPIC_API_KEY" ] && echo "yes (${#ANTHROPIC_API_KEY} chars, prefix=${ANTHROPIC_API_KEY:0:7}...)" || echo "NO")"
echo "CLAUDE_CODE_OAUTH_TOKEN set: $([ -n "$CLAUDE_CODE_OAUTH_TOKEN" ] && echo "yes (${#CLAUDE_CODE_OAUTH_TOKEN} chars, prefix=${CLAUDE_CODE_OAUTH_TOKEN:0:7}...)" || echo "NO")"
echo "GITHUB_TOKEN set: $([ -n "$GITHUB_TOKEN" ] && echo "yes (${#GITHUB_TOKEN} chars)" || echo "NO")"
echo "LINEAR_API_KEY set: $([ -n "$LINEAR_API_KEY" ] && echo "yes (${#LINEAR_API_KEY} chars)" || echo "NO")"
echo "ISSUE_PROMPT set: $([ -n "$ISSUE_PROMPT" ] && echo "yes (${#ISSUE_PROMPT} chars)" || echo "NO")"

git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
echo "Git credential helper configured"

envsubst < /app/mcp_config.template.json > /tmp/mcp_config.json
echo "MCP config rendered:"
cat /tmp/mcp_config.json | sed 's/"GITHUB_PERSONAL_ACCESS_TOKEN": "[^"]*"/"GITHUB_PERSONAL_ACCESS_TOKEN": "***"/g' | sed 's/"LINEAR_API_KEY": "[^"]*"/"LINEAR_API_KEY": "***"/g'

echo "=== Launching claude ==="
echo "claude version: $(claude --version 2>&1 || echo 'unknown')"

claude --mcp-config /tmp/mcp_config.json \
       --allowedTools "mcp__github__*,mcp__linear__*,Read,Write,Edit,Bash,Glob,Grep" \
       -p "$ISSUE_PROMPT" \
       --output-format stream-json \
       --verbose
EXIT_CODE=$?

echo "=== Claude exited with code $EXIT_CODE ==="

# Kill the entire process tree. In a container, bash is PID 1 and orphaned
# MCP server processes (npx -> node) prevent the container from exiting.
# SIGKILL the whole tree since these are disposable processes.
kill -9 -1 2>/dev/null || true
exit $EXIT_CODE
