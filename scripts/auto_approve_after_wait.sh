#!/usr/bin/env bash
# Wait for a reviewer to act on the gated `video` job, then auto-approve any
# still-pending deployment for this run. Designed to run in parallel with the
# gated video job: if the reviewer approves/rejects/edit-comments within the
# window, the deployment is no longer pending by the time this wakes up and
# we exit cleanly. If they don't act, we approve and the video builds.
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

WAIT_SECONDS="${WAIT_SECONDS:-1800}"   # 30 min default
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY not set}"
RUN_ID="${GITHUB_RUN_ID:?GITHUB_RUN_ID not set}"

if [ -z "${GH_TOKEN:-}" ]; then
  echo "AUTO_APPROVE_PAT not configured; auto-approve disabled."
  echo "The video job will remain blocked until manually approved/rejected."
  exit 0
fi

echo "Waiting ${WAIT_SECONDS}s for reviewer to approve / reject / edit..."
sleep "$WAIT_SECONDS"

# Each pending deployment exposes its target environment. Approving by
# environment_id approves every pending deployment in this run that targets
# that environment (covers matrix workflows where N jobs share one env).
pending=$(gh api "repos/$REPO/actions/runs/$RUN_ID/pending_deployments" \
  --jq '[.[].environment.id] | unique')

if [ -z "$pending" ] || [ "$pending" = "[]" ]; then
  echo "No pending deployments — reviewer already acted. Done."
  exit 0
fi

echo "Auto-approving environment IDs: $pending"
for env_id in $(echo "$pending" | jq -r '.[]'); do
  gh api "repos/$REPO/actions/runs/$RUN_ID/pending_deployments" \
    -X POST \
    -f "environment_ids[]=$env_id" \
    -f "state=approved" \
    -f "comment=Auto-approved after ${WAIT_SECONDS}s reviewer timeout."
done
