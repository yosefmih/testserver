#!/bin/bash
set -e

echo "$GITHUB_TOKEN" | gh auth login --with-token

envsubst < /app/mcp_config.template.json > /tmp/mcp_config.json

claude --mcp-config /tmp/mcp_config.json \
       --allowedTools "mcp__github__*,mcp__linear__*,Read,Write,Edit,Bash,Glob,Grep" \
       -p "$ISSUE_PROMPT" \
       --output-format text
