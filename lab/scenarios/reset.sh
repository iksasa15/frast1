#!/usr/bin/env bash
# Manual fallback: reset lab via lab agent
set -euo pipefail
AGENT="${LAB_AGENT_URL:-http://127.0.0.1:9000}"
TOKEN="${LAB_AGENT_TOKEN:?LAB_AGENT_TOKEN is required}"
curl -sf -X POST "$AGENT/reset" -H "x-agent-token: $TOKEN"
echo
