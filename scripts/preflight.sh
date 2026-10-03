#!/usr/bin/env bash
set -uo pipefail
ok(){ printf "  \033[32m✔\033[0m %s\n" "$1"; }
bad(){ printf "  \033[31m✘\033[0m %s\n" "$1"; FAIL=1; }

FAIL=0
API=${ROOTIQ_API:-http://localhost:8000}
UI=${ROOTIQ_UI:-http://localhost:8080}

echo "RootIQ live preflight"
HEALTH=$(curl -fsS -m 5 "$API/api/health" 2>/dev/null) || HEALTH=""
[ -n "$HEALTH" ] && ok "backend reachable" || bad "backend unreachable"
curl -fsS -m 5 "$UI" >/dev/null 2>&1 && ok "frontend reachable" || bad "frontend unreachable"

STATE=$(printf '%s' "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('discovery',{}).get('state','?'))" 2>/dev/null || echo "?")
FRESH=$(printf '%s' "$HEALTH" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('discovery',{}).get('fresh',False)).lower())" 2>/dev/null || echo "false")
[ "$STATE" = "live" ] && [ "$FRESH" = "true" ] && ok "topology discovery is live and fresh" || bad "topology discovery state=$STATE fresh=$FRESH"

curl -fsS -m 5 "$API/api/topology" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['nodes']; print('  topology:',len(d['nodes']),'nodes,',len(d['links']),'links')" \
  && ok "observed topology is non-empty" || bad "observed topology is empty"

exit $FAIL
