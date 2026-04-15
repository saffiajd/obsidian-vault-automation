#!/bin/zsh
INPUT=$(cat)
CWD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))")
DURATION=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('duration_seconds',0))")

VAULT_PATH="/Users/jonathansaffian/Desktop/OpenClaw/Claude"
PROJECT=$(basename "$CWD")
TODAY=$(date +%Y-%m-%d)
SESSIONS_DIR="$VAULT_PATH/Sessions"

STUB_FILE="$SESSIONS_DIR/${TODAY}-${PROJECT}-session-stub.md"

FILES_CHANGED=""
if git -C "$CWD" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  FILES_CHANGED=$(git -C "$CWD" diff --name-only 2>/dev/null | head -20)
fi

DURATION_MIN=$((DURATION / 60))

cat > "$STUB_FILE" << STUB
---
date: $TODAY
project: $PROJECT
tags: [session-stub, $PROJECT]
type: session-stub
duration_minutes: $DURATION_MIN
---

# Session Stub: $PROJECT ($TODAY)

**This is an auto-generated metadata stub, not a full session log.**
If Claude wrote a full session log, it will be a separate file in this folder.

## Metadata
- Duration: ${DURATION_MIN} minutes
- Project directory: $CWD

## Files Changed
$FILES_CHANGED
STUB
