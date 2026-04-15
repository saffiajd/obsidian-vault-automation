#!/bin/zsh
INPUT=$(cat)
CWD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))")

VAULT_PATH="/Users/jonathansaffian/Desktop/OpenClaw/Claude"
PROJECT=$(basename "$CWD")
SESSIONS_DIR="$VAULT_PATH/Sessions"
TOPICS_DIR="$VAULT_PATH/Topics"

LAST_LOG=$(ls -t "$SESSIONS_DIR"/*.md 2>/dev/null | grep -i "\b${PROJECT}\b" | grep -v "session-stub" | head -1)
LAST_LOG_SUMMARY=""
LAST_LOG_NAME=""
if [ -n "$LAST_LOG" ]; then
  LAST_LOG_NAME=$(basename "$LAST_LOG" .md)
  LAST_LOG_SUMMARY=$(sed -n '/^## Summary/,/^## /p' "$LAST_LOG" | head -5)
fi

RECENT_PROJECT=$(ls -t "$SESSIONS_DIR"/*.md 2>/dev/null | grep -i "\b${PROJECT}\b" | grep -v "session-stub" | head -5 | while read -r f; do basename "$f" .md; done)

RECENT_ALL=$(ls -t "$SESSIONS_DIR"/*.md 2>/dev/null | grep -v "session-stub" | head -10 | while read -r f; do basename "$f" .md; done)

TOPIC_NAMES=$(find "$TOPICS_DIR" -maxdepth 1 -name "*.md" 2>/dev/null | while read -r f; do basename "$f" .md; done | tr '\n' ', ' | sed 's/,$//')

cat << CONTEXT
VAULT CONTEXT (auto-loaded):
Last session: $LAST_LOG_NAME
$LAST_LOG_SUMMARY
Recent sessions (this project): $RECENT_PROJECT
Recent sessions (all projects): $RECENT_ALL
Known topics: $TOPIC_NAMES

REMINDER: Your Obsidian vault has session logs, topic notes, and conversation exports for most projects. ALWAYS search the vault BEFORE cloning repos, exploring codebases, or doing web research. Use mcp__obsidian__search_notes or mcp__smart-connections__lookup to find answers fast.
CONTEXT
