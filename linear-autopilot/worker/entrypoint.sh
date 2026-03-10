#!/bin/bash
set -e

# gh CLI auto-detects GITHUB_TOKEN from the environment, no login needed.
# Configure git to use the token for HTTPS cloning.
git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"

envsubst < /app/mcp_config.template.json > /tmp/mcp_config.json

claude --mcp-config /tmp/mcp_config.json \
       --allowedTools "mcp__github__*,mcp__linear__*,Read,Write,Edit,Bash,Glob,Grep" \
       -p "$ISSUE_PROMPT" \
       --output-format text
