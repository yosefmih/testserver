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
# Presence only — never log secret values, lengths, or prefixes (logs go to Loki + the UI).
claude_auth=missing
[ -n "$CLAUDE_CODE_OAUTH_TOKEN" ] && claude_auth=CLAUDE_CODE_OAUTH_TOKEN
[ -n "$ANTHROPIC_API_KEY" ] && claude_auth=ANTHROPIC_API_KEY
echo "Claude auth: ${claude_auth}"
echo "GITHUB_TOKEN: $([ -n "$GITHUB_TOKEN" ] && echo set || echo missing)"
echo "LINEAR_API_KEY: $([ -n "$LINEAR_API_KEY" ] && echo set || echo missing)"
echo "ISSUE_PROMPT: $([ -n "$ISSUE_PROMPT" ] && echo set || echo missing)"
echo "CALLBACK_URL: $([ -n "$CALLBACK_URL" ] && echo set || echo missing)"
echo "CALLBACK_TOKEN: $([ -n "$CALLBACK_TOKEN" ] && echo set || echo missing)"
echo "RUN_KIND: ${RUN_KIND:-unset}"

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
    --model "${CLAUDE_MODEL:-claude-opus-4-8}"
    --mcp-config /tmp/mcp_config.json
    --allowedTools "${ALLOWED_TOOLS:-mcp__github__*,mcp__linear__get_issue,mcp__linear__get_issue_comments,Read,Write,Edit,Bash,Glob,Grep}"
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
