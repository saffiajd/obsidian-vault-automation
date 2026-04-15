# Obsidian Vault Automation

Self-healing automation scripts for an Obsidian "second brain" vault fed by Claude Code and OpenClaw. Built with [The Obsidian Prompt v4.1.0](https://dontsleeponai.com/obsidian-claude-code).

## What's in here

| Directory | Contents |
|-----------|----------|
| `scripts/` | `topic-linker.py` — adds/updates "See Also" WikiLink footers every 10 min; `vault-health.py` — daily health check report |
| `hooks/` | Claude Code session hooks (SessionStart context loader, SessionEnd safety net, PreCompact reminder) |
| `config/` | Shared config for linker + health check (`config.json`) |
| `launchagents/` | macOS LaunchAgent plists for background services |

## How it works

- **topic-linker.py** runs every 10 minutes via LaunchAgent. It scans vault folders for markdown files, matches content against topic notes in `Topics/`, and appends `## See Also` footers with `[[WikiLinks]]`. Uses atomic writes, `fcntl.flock` locking, and mtime-based change detection.
- **vault-health.py** runs daily at 8 AM. It checks linker health, orphan file counts, Claude Vault status, and writes a `vault-health.md` report into the vault root.
- **Session hooks** fire on Claude Code events — loading vault context at session start, saving metadata stubs at session end, and reminding about interim logs on context compaction.

## Setup

1. Replace `__VAULT_PATH__` in `config/config.json` with your actual vault path.
2. Replace `__HOME__` in `launchagents/*.plist` with your home directory path.
3. Copy files to their destinations:

```bash
# Scripts
cp scripts/*.py ~/claude-vault/
chmod +x ~/claude-vault/topic-linker.py ~/claude-vault/vault-health.py

# Config
mkdir -p ~/.config/topic-linker
cp config/config.json ~/.config/topic-linker/

# Hooks
mkdir -p ~/.claude/hooks
cp hooks/*.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.sh

# LaunchAgents (macOS only)
cp launchagents/*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.obsidian.topic-linker.plist
launchctl load ~/Library/LaunchAgents/com.obsidian.vault-health.plist
launchctl load ~/Library/LaunchAgents/com.claudevault.watch.plist
```

4. Update vault path in hook scripts (`session-safety-net.sh`, `vault-context-loader.sh`, `post-compact-reminder.sh`).

## Requirements

- Python 3 (stdlib only — no pip dependencies)
- macOS (for LaunchAgents) or Linux (translate to systemd user timers)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) for hooks
- [Claude Vault](https://github.com/MarioPadilla/claude-vault) for conversation export
- Obsidian with the vault structure: `Sessions/`, `Topics/`, `Conversations/`, `OpenClaw/`, `Archive/`, `Resources/`, `Templates/`

## License

MIT
