#!/usr/bin/env bash
# Setup a freshly-created repo with kadalz's default GitHub configuration.
# Usage: ./setup.sh <owner/repo>
# Requires: gh authenticated. Run from anywhere.
set -euo pipefail

REPO="${1:?usage: ./setup.sh <owner/repo>}"
OWNER="${REPO%%/*}"

echo "==> Configuring $REPO"

# required_signatures + ALL rulesets/branch-protection need GitHub Pro on private repos (free tier: public only)
VISIBILITY=$(gh api "repos/$REPO" --jq .visibility)

# --- Branch protection: protect-main ruleset (free tier: public repos only) ---
if [ "$VISIBILITY" = "public" ]; then
  RULESET_JSON=$(mktemp)
  cat > "$RULESET_JSON" <<'EOF'
{
  "name": "protect-main",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [{ "context": "ci" }]
      }
    },
    { "type": "required_signatures" }
  ]
}
EOF
  echo "==> Creating ruleset protect-main"
  gh api --method POST "repos/$REPO/rulesets" --input "$RULESET_JSON" >/dev/null && echo "    OK"
  rm -f "$RULESET_JSON"
else
  echo "==> SKIP ruleset: branch protection needs GitHub Pro on private repos"
  echo "    (upgrade to Pro to enable protect-main, or make the repo public)"
fi

# --- Repo settings via PATCH ---
echo "==> Applying repo settings"
gh api --method PATCH "repos/$REPO" \
  -f "delete_branch_on_merge=true" \
  -f "allow_squash_merge=true" \
  -f "allow_rebase_merge=true" \
  -f "allow_merge_commit=false" \
  -f "allow_auto_merge=false" >/dev/null && echo "    OK"

# --- Default labels (issue templates reference them) ---
echo "==> Ensuring labels"
gh label create bug -c d73a4a -R "$REPO" >/dev/null 2>&1 || true
gh label create enhancement -c a2eeef -R "$REPO" >/dev/null 2>&1 || true
gh label create good-first-issue -c 7057ff -R "$REPO" >/dev/null 2>&1 || true
echo "    OK"

echo "==> Done. Manual (web UI, once):"
if [ "$VISIBILITY" = "public" ]; then
  echo "    Security -> Advanced Security: CodeQL default setup ON, secret scanning push protection ON"
  echo "    (Advanced Security needs public repos on free tier; visible after first push)"
else
  echo "    Branch protection (ruleset), CodeQL, secret-scanning push protection all need"
  echo "    GitHub Pro on private repos. Skip unless you upgrade."
fi
