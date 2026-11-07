#!/usr/bin/env bash
# Deterministic publish tail for the Maoty Friday refresh.
#
# This owns the steps that must not depend on a model remembering them:
# validating taste labels, building, staging exactly one data file,
# committing, pushing with one transient-network retry, and reporting.
#
# Usage:
#   scripts/publish.sh              # validate, build, commit, push
#   scripts/publish.sh --dry-run    # validate + build only; no commit/push
#
# Exit codes:
#   0  ok (published, or nothing to publish)
#   1  taste labels invalid (null value or duplicate aoty_url)
#   2  build failed
#   3  commit failed
#   4  push failed
#
# The weekly agent workflow is: `bun run albums` -> assign taste_label to any
# album reported as needing one -> `scripts/publish.sh`.

set -uo pipefail

# Cron runs with a minimal PATH; make the usual tool locations explicit.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALBUM_DATA="$ROOT/src/data/album-list.json"
REMOTE_BRANCH="main"
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$arg" >&2
      exit 64
      ;;
  esac
done

cd "$ROOT" || exit 66

if ! command -v bun >/dev/null 2>&1; then
  printf '{"error": "bun not found on PATH"}\n' >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  printf '{"error": "python3 not found on PATH"}\n' >&2
  exit 1
fi

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"
}

report_field() {
  # report_field <name> <json-literal-value>
  printf '%s' "\"$1\": $2"
}

# --- 1. taste label validation -------------------------------------------
# The label assignment is the only editorial step; this gate is what makes it
# impossible to publish an unlabeled album silently.
LABEL_CHECK="$(python3 - "$ALBUM_DATA" <<'PY'
import json
import sys
from collections import Counter

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    albums = json.load(handle)

valid = {"It's a match", "Just for you", "Maybe you'll like it"}
missing = [
    f"{a.get('artist')} - {a.get('album')}"
    for a in albums
    if a.get("taste_label") not in valid
]
urls = Counter(a.get("aoty_url") for a in albums if a.get("aoty_url"))
duplicates = sorted(url for url, count in urls.items() if count > 1)

print(json.dumps({"missing": missing, "duplicates": duplicates}))
PY
)"

MISSING_COUNT="$(printf '%s' "$LABEL_CHECK" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["missing"]))')"
DUPLICATE_COUNT="$(printf '%s' "$LABEL_CHECK" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["duplicates"]))')"

if [ "$MISSING_COUNT" != "0" ] || [ "$DUPLICATE_COUNT" != "0" ]; then
  printf '\n=== MAOTY PUBLISH REPORT ===\n'
  printf '{"taste_labels": "invalid", "albums_missing_taste_label": %s, "duplicate_aoty_urls": %s, "detail": %s, "build": "skipped", "commit": "skipped", "push": "skipped"}\n' \
    "$MISSING_COUNT" "$DUPLICATE_COUNT" "$LABEL_CHECK"
  printf '\nAssign a valid taste_label to every album listed above, then rerun scripts/publish.sh.\n' >&2
  exit 1
fi

# --- 2. build -------------------------------------------------------------
BUILD_LOG="$(mktemp -t maoty-build)"
if ! bun run build >"$BUILD_LOG" 2>&1; then
  printf '\n=== MAOTY PUBLISH REPORT ===\n'
  printf '{"taste_labels": "ok", "build": "failed", "build_log": %s, "commit": "skipped", "push": "skipped"}\n' "$(json_escape "$(tail -c 2000 "$BUILD_LOG")")"
  printf '\nBuild failed; nothing committed or pushed. Log: %s\n' "$BUILD_LOG" >&2
  exit 2
fi
rm -f "$BUILD_LOG"

# --- 3. stage -------------------------------------------------------------
# Only the generated dataset belongs to a normal weekly refresh. Anything else
# in the working tree is left untouched for the user to review.
git -C "$ROOT" add -- "$ALBUM_DATA"

if git -C "$ROOT" diff --cached --quiet -- "$ALBUM_DATA"; then
  printf '\n=== MAOTY PUBLISH REPORT ===\n'
  printf '{"taste_labels": "ok", "build": "passed", "changes": "none", "commit": "skipped", "push": "skipped"}\n'
  exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
  printf '\n=== MAOTY PUBLISH REPORT ===\n'
  printf '{"taste_labels": "ok", "build": "passed", "changes": "pending", "dry_run": true, "commit": "skipped", "push": "skipped"}\n'
  exit 0
fi

# --- 4. commit ------------------------------------------------------------
COMMIT_MSG="Refresh Maoty albums for $(date +%Y-%m-%d)"
if ! git -C "$ROOT" commit -q -m "$COMMIT_MSG" -- "$ALBUM_DATA"; then
  printf '\n=== MAOTY PUBLISH REPORT ===\n'
  printf '{"taste_labels": "ok", "build": "passed", "commit": "failed", "push": "skipped"}\n'
  exit 3
fi
COMMIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD)"

# --- 5. push, with one transient-network retry ---------------------------
PUSH_LOG="$(mktemp -t maoty-push)"
push_once() {
  git -C "$ROOT" push origin "$REMOTE_BRANCH" >"$PUSH_LOG" 2>&1
}

PUSHED=0
if push_once; then
  PUSHED=1
else
  if grep -Eiq 'could not resolve host|temporary failure in name resolution|connection timed out|operation timed out|network is unreachable|connection reset' "$PUSH_LOG"; then
    sleep 5
    if push_once; then
      PUSHED=1
    fi
  fi
fi

if [ "$PUSHED" = "1" ]; then
  rm -f "$PUSH_LOG"
  printf '\n=== MAOTY PUBLISH REPORT ===\n'
  printf '{"taste_labels": "ok", "build": "passed", "commit": %s, "push": "succeeded"}\n' "$(json_escape "$COMMIT_SHA")"
  exit 0
fi

# --- 6. push failed: distinguish auth from connectivity ------------------
SSH_DIAG="$(ssh -T -o BatchMode=yes -o ConnectTimeout=10 git@github.com 2>&1 | head -3 | tr '\n' ' ')"
printf '\n=== MAOTY PUBLISH REPORT ===\n'
printf '{"taste_labels": "ok", "build": "passed", "commit": %s, "push": "failed", "push_error": %s, "ssh_diagnostic": %s, "blocker": %s}\n' \
  "$(json_escape "$COMMIT_SHA")" \
  "$(json_escape "$(tail -c 1000 "$PUSH_LOG")")" \
  "$(json_escape "$SSH_DIAG")" \
  "$(json_escape "commit $COMMIT_SHA exists locally but could not be pushed")"
rm -f "$PUSH_LOG"
printf '\nPush failed. The commit exists locally and must be pushed manually.\n' >&2
exit 4
