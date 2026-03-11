#!/bin/bash

cleanup() {
    trap - SIGTERM SIGINT
    echo "=== Received signal, shutting down ==="
    kill -TERM "$CLAUDE_PID" 2>/dev/null
    sleep 2
    kill -KILL "$CLAUDE_PID" 2>/dev/null
    exit 143
}
trap cleanup SIGTERM SIGINT

echo "=== Worker entrypoint starting ==="
echo "CLAUDE_CODE_OAUTH_TOKEN set: $([ -n "$CLAUDE_CODE_OAUTH_TOKEN" ] && echo "yes (${#CLAUDE_CODE_OAUTH_TOKEN} chars, prefix=${CLAUDE_CODE_OAUTH_TOKEN:0:7}...)" || echo "NO")"
echo "GITHUB_TOKEN set: $([ -n "$GITHUB_TOKEN" ] && echo "yes (${#GITHUB_TOKEN} chars)" || echo "NO")"
echo "LINEAR_API_KEY set: $([ -n "$LINEAR_API_KEY" ] && echo "yes (${#LINEAR_API_KEY} chars)" || echo "NO")"
echo "ISSUE_PROMPT set: $([ -n "$ISSUE_PROMPT" ] && echo "yes (${#ISSUE_PROMPT} chars)" || echo "NO")"
echo "CALLBACK_URL set: $([ -n "$CALLBACK_URL" ] && echo "yes" || echo "NO")"
echo "CALLBACK_TOKEN set: $([ -n "$CALLBACK_TOKEN" ] && echo "yes (${#CALLBACK_TOKEN} chars)" || echo "NO")"
echo "RUN_KIND set: $([ -n "$RUN_KIND" ] && echo "$RUN_KIND" || echo "NO")"

export HOME=/workspace

git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
echo "Git credential helper configured"

envsubst < /app/mcp_config.template.json > /tmp/mcp_config.json
echo "MCP config:"
node -e 'const j=JSON.parse(require("fs").readFileSync("/tmp/mcp_config.json","utf8"));for(const s of Object.values(j.mcpServers||{})){for(const k of Object.keys(s.env||{}))s.env[k]="***";}console.log(JSON.stringify(j,null,2))'

cd /workspace 2>/dev/null || true

echo "=== Launching claude ==="
echo "claude version: $(claude --version 2>&1 || echo 'unknown')"

CLAUDE_ARGS=(
    --mcp-config /tmp/mcp_config.json
    --allowedTools "mcp__github__*,mcp__linear__get_issue,mcp__linear__get_issue_comments,Read,Write,Edit,Bash,Glob,Grep"
    --output-format stream-json
    --verbose
)

HAS_SESSION=false
if [ -d "/workspace/.claude" ]; then
    HAS_SESSION=true
    echo "=== Found existing session in /workspace/.claude, will continue ==="
fi

if [ "$HAS_SESSION" = true ] && [ "$RUN_KIND" = "review" ]; then
    claude "${CLAUDE_ARGS[@]}" --continue -p "$ISSUE_PROMPT" 2>&1 &
else
    claude "${CLAUDE_ARGS[@]}" -p "$ISSUE_PROMPT" 2>&1 &
fi
CLAUDE_PID=$!

wait $CLAUDE_PID
EXIT_CODE=$?

echo "=== Claude exited with code $EXIT_CODE ==="

trap - SIGTERM SIGINT
kill -TERM "$CLAUDE_PID" 2>/dev/null
sleep 1
kill -9 "$CLAUDE_PID" 2>/dev/null
exit $EXIT_CODE
