#!/bin/bash

echo "=== Worker entrypoint starting ==="
echo "CLAUDE_CODE_OAUTH_TOKEN set: $([ -n "$CLAUDE_CODE_OAUTH_TOKEN" ] && echo "yes (${#CLAUDE_CODE_OAUTH_TOKEN} chars, prefix=${CLAUDE_CODE_OAUTH_TOKEN:0:7}...)" || echo "NO")"
echo "GITHUB_TOKEN set: $([ -n "$GITHUB_TOKEN" ] && echo "yes (${#GITHUB_TOKEN} chars)" || echo "NO")"
echo "LINEAR_API_KEY set: $([ -n "$LINEAR_API_KEY" ] && echo "yes (${#LINEAR_API_KEY} chars)" || echo "NO")"
echo "ISSUE_PROMPT set: $([ -n "$ISSUE_PROMPT" ] && echo "yes (${#ISSUE_PROMPT} chars)" || echo "NO")"
echo "CALLBACK_URL set: $([ -n "$CALLBACK_URL" ] && echo "yes" || echo "NO")"
echo "CALLBACK_TOKEN set: $([ -n "$CALLBACK_TOKEN" ] && echo "yes (${#CALLBACK_TOKEN} chars)" || echo "NO")"

git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
echo "Git credential helper configured"

envsubst < /app/mcp_config.template.json > /tmp/mcp_config.json
echo "MCP config:"
node -e 'const j=JSON.parse(require("fs").readFileSync("/tmp/mcp_config.json","utf8"));for(const s of Object.values(j.mcpServers||{})){for(const k of Object.keys(s.env||{}))s.env[k]="***";}console.log(JSON.stringify(j,null,2))'

# Start in the persistent workspace volume
cd /workspace 2>/dev/null || true

echo "=== Launching claude ==="
echo "claude version: $(claude --version 2>&1 || echo 'unknown')"

# Run claude without set -e so we always reach cleanup even on failure.
# Claude's stream-json output goes to stdout and is captured by sandbox logs.
claude --mcp-config /tmp/mcp_config.json \
       --allowedTools "mcp__github__*,mcp__linear__get_issue,mcp__linear__get_issue_comments,Read,Write,Edit,Bash,Glob,Grep" \
       -p "$ISSUE_PROMPT" \
       --output-format stream-json \
       --verbose 2>&1
EXIT_CODE=$?

echo "=== Claude exited with code $EXIT_CODE ==="

# Kill the entire process tree. In a container, bash is PID 1 and orphaned
# MCP server processes (npx -> node) prevent the container from exiting.
kill -9 -1 2>/dev/null || true
exit $EXIT_CODE
