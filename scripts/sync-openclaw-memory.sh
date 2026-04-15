#!/bin/zsh
# sync-openclaw-memory.sh — Syncs OpenClaw bot workspaces to Obsidian vault
# Runs every 5 minutes via LaunchAgent

VAULT_PATH="/Users/jonathansaffian/Desktop/OpenClaw/Claude"
LOG="$HOME/claude-vault/memory-sync.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"; }

log "Starting OpenClaw memory sync"

# Discover bot workspaces
BOT_DIRS=()
for d in ~/clawd* ~/malcolm; do
  [ -d "$d" ] && BOT_DIRS+=("$d")
done

if [ ${#BOT_DIRS[@]} -eq 0 ]; then
  log "No bot workspaces found — nothing to sync"
  exit 0
fi

for BOT_DIR in "${BOT_DIRS[@]}"; do
  BOT_NAME=$(basename "$BOT_DIR")
  log "Syncing bot: $BOT_NAME from $BOT_DIR"

  # Sync MEMORY.md
  if [ -f "$BOT_DIR/MEMORY.md" ]; then
    mkdir -p "$VAULT_PATH/OpenClaw/Memory"
    cp -p "$BOT_DIR/MEMORY.md" "$VAULT_PATH/OpenClaw/Memory/${BOT_NAME}-MEMORY.md"
    log "  Synced MEMORY.md"
  fi

  # Sync ACTIVE.md
  if [ -f "$BOT_DIR/ACTIVE.md" ]; then
    mkdir -p "$VAULT_PATH/OpenClaw/ActiveTasks"
    cp -p "$BOT_DIR/ACTIVE.md" "$VAULT_PATH/OpenClaw/ActiveTasks/${BOT_NAME}-ACTIVE.md"
    log "  Synced ACTIVE.md"
  fi

  # Sync daily notes (any .md files that look like daily notes)
  DAILY_DIR="$BOT_DIR/daily"
  if [ -d "$DAILY_DIR" ]; then
    mkdir -p "$VAULT_PATH/OpenClaw/DailyNotes/$BOT_NAME"
    rsync -a --update "$DAILY_DIR/"*.md "$VAULT_PATH/OpenClaw/DailyNotes/$BOT_NAME/" 2>/dev/null
    log "  Synced daily notes"
  fi
done

log "Sync complete"
