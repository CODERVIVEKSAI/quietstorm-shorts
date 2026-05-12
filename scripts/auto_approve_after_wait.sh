#!/usr/bin/env bash
# Poll for the gated `video` deployment until the reviewer acts. Exit as soon
# as the deployment leaves the pending state (approve/reject/edit-comment),
# or auto-approve once $WAIT_SECONDS has elapsed without any action. Runs in
# parallel with the gated video job.
#
# PAT setup (one-time — required because GitHub's default GITHUB_TOKEN cannot
# approve its own workflow's deployments):
#   1. Create a fine-grained Personal Access Token scoped to this repo with:
#        - Actions: read & write
#        - Deployments: read & write
#   2. Save it as a repo secret named AUTO_APPROVE_PAT.
#   3. Confirm the manual-approval environment has "Prevent self-review" OFF
#      (Settings → Environments → manual-approval).
#
# If AUTO_APPROVE_PAT is not set, this script logs a notice and exits; the
# video job stays blocked on manual approval as before (no regression).

set -euo pipefail

WAIT_SECONDS="${WAIT_SECONDS:-1800}"       # 30 min total budget
POLL_INTERVAL="${POLL_INTERVAL:-30}"       # check every 30s
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY not set}"
RUN_ID="${GITHUB_RUN_ID:?GITHUB_RUN_ID not set}"

if [ -z "${GH_TOKEN:-}" ]; then
  echo "AUTO_APPROVE_PAT not configured; auto-approve disabled."
  echo "The video job will remain blocked until manually approved/rejected."
  exit 0
fi

list_pending() {
  gh api "repos/$REPO/actions/runs/$RUN_ID/pending_deployments" \
    --jq '[.[].environment.id] | unique'
}

deadline=$(( $(date +%s) + WAIT_SECONDS ))
pending="$(list_pending)"

while [ -n "$pending" ] && [ "$pending" != "[]" ]; do
  now=$(date +%s)
  remaining=$(( deadline - now ))
  if [ "$remaining" -le 0 ]; then
    echo "Timeout reached. Auto-approving environment IDs: $pending"
    for env_id in $(echo "$pending" | jq -r '.[]'); do
      gh api "repos/$REPO/actions/runs/$RUN_ID/pending_deployments" \
        -X POST \
        -f "environment_ids[]=$env_id" \
        -f "state=approved" \
        -f "comment=Auto-approved after ${WAIT_SECONDS}s reviewer timeout."
    done
    exit 0
  fi
  sleep_for=$POLL_INTERVAL
  if [ "$remaining" -lt "$sleep_for" ]; then sleep_for=$remaining; fi
  echo "Still pending; next check in ${sleep_for}s (timeout in ${remaining}s)..."
  sleep "$sleep_for"
  pending="$(list_pending)"
done

echo "Reviewer acted — deployment is no longer pending. Exiting cleanly."
