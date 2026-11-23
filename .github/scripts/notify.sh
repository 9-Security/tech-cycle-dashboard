#!/usr/bin/env bash
# Open / update / close GitHub issues that report the state of the daily refresh.
#
#   notify.sh <label> <state> <title> <body>
#     state = fail : open an issue with <label>, or comment on the open one
#     state = ok   : comment "recovered" on the open issue with <label> and close it
#
# Needs GH_TOKEN (issues: write) and REPO (owner/name). Only fixed strings,
# run links and step names go into issues - never log text or error messages.
set -euo pipefail
label="$1"; state="$2"; title="$3"; body="$4"

open=$(gh api "repos/${REPO}/issues?state=open&labels=${label}&per_page=1" --jq '.[0].number // empty')

if [ "$state" = "fail" ]; then
  if [ -n "$open" ]; then
    gh api -X POST "repos/${REPO}/issues/${open}/comments" -f body="$body" > /dev/null
    echo "commented on #${open}"
  else
    gh api -X POST "repos/${REPO}/labels" -f name="$label" -f color="d73a4a" > /dev/null 2>&1 || true
    num=$(gh api -X POST "repos/${REPO}/issues" -f title="$title" -f body="$body" -f "labels[]=$label" --jq '.number')
    echo "opened #${num}"
  fi
elif [ "$state" = "ok" ]; then
  if [ -n "$open" ]; then
    gh api -X POST "repos/${REPO}/issues/${open}/comments" -f body="$body" > /dev/null
    gh api -X PATCH "repos/${REPO}/issues/${open}" -f state=closed -f state_reason=completed > /dev/null
    echo "closed #${open}"
  else
    echo "nothing to close"
  fi
else
  echo "unknown state: $state" >&2; exit 2
fi
