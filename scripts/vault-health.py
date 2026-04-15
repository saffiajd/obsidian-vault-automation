#!/usr/bin/env python3
# vault-health v4.1.0
"""
Daily health check for Obsidian vault self-healing system.
Writes vault-health.md with status of all components.
"""

import argparse, fcntl, json, logging, os, re, subprocess, sys, tempfile, time
from datetime import datetime

VERSION = "4.1.0"
FOOTER_START = "<!-- topic-linker:start -->"
REQUIRED_CONFIG_KEYS = ["vault_path", "topics_folder", "skip_folders", "lockfile", "mtime_db"]

def expand_path(p):
    return os.path.expandvars(os.path.expanduser(p))

def load_config(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    for key in REQUIRED_CONFIG_KEYS:
        if key not in config:
            raise ValueError(f"Missing required config key: {key}")
    return config

def atomic_write(path, content):
    dir_name = os.path.dirname(path)
    os.makedirs(dir_name, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=dir_name, suffix='.tmp',
                                     delete=False, encoding='utf-8') as f:
        f.write(content)
        tmp_path = f.name
    os.rename(tmp_path, path)

def newest_file_age_days(folder_path):
    if not os.path.isdir(folder_path):
        return None
    newest = 0
    found = False
    for root, dirs, files in os.walk(folder_path):
        for fn in files:
            if fn.endswith('.md'):
                try:
                    mt = os.path.getmtime(os.path.join(root, fn))
                    if mt > newest:
                        newest = mt
                        found = True
                except OSError:
                    continue
    return (time.time() - newest) / 86400.0 if found else None

def check_vault_health(config_path=None, vault_path=None):
    """Extractable health check function. Works with config or vault_path bootstrap."""
    if config_path and os.path.exists(expand_path(config_path)):
        try:
            config = load_config(expand_path(config_path))
        except (json.JSONDecodeError, ValueError) as e:
            return {"error": f"Config error: {e}"}
    elif vault_path:
        config = {"vault_path": vault_path, "topics_folder": "Topics",
                  "skip_folders": [".obsidian", ".git", ".smart-env", "Templates", "Topics"],
                  "lockfile": "", "mtime_db": "", "thresholds": {}}
    else:
        return {"error": "No config or vault path provided"}
    vp = expand_path(config["vault_path"])
    th = config.get("thresholds", {})
    results = {}
    # Linker recency
    mtime_path = expand_path(config.get("mtime_db", ""))
    if mtime_path and os.path.exists(mtime_path):
        age_h = (time.time() - os.path.getmtime(mtime_path)) / 3600
        results["linker_recency"] = ("OK" if age_h < 24 else "WARN" if age_h < 48 else "CRIT",
                                     f"Last run {age_h:.1f}h ago")
    else:
        results["linker_recency"] = ("CRIT", "mtime.json missing")
    # Lockfile
    lf = expand_path(config.get("lockfile", ""))
    if lf and os.path.exists(lf):
        try:
            fd = open(lf, 'r+')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
                fd.close()
                age_m = (time.time() - os.path.getmtime(lf)) / 60
                stale = th.get("lockfile_stale_minutes", 60)
                results["lockfile"] = ("CRIT", f"Stale ({age_m:.0f}m)") if age_m > stale else ("OK", "Clean")
            except (BlockingIOError, OSError):
                fd.close()
                results["lockfile"] = ("OK", "Active (linker running)")
        except OSError:
            results["lockfile"] = ("OK", "Clean")
    else:
        results["lockfile"] = ("OK", "Clean")
    # Orphans
    skip = config.get("skip_folders", [])
    total = orphans = 0
    try:
        for e in os.scandir(vp):
            if e.is_dir(follow_symlinks=False) and e.name not in skip:
                for root, dirs, files in os.walk(os.path.join(vp, e.name)):
                    for fn in files:
                        if fn.endswith('.md'):
                            total += 1
                            try:
                                with open(os.path.join(root, fn), 'r', encoding='utf-8') as f:
                                    if FOOTER_START not in f.read():
                                        orphans += 1
                            except (OSError, UnicodeDecodeError):
                                orphans += 1
    except OSError:
        pass
    if total > 0:
        pct = orphans / total * 100
        small = total < th.get("small_vault_threshold", 50)
        warn = th.get("orphan_pct_warn_small_vault" if small else "orphan_pct_warn", 5)
        crit = th.get("orphan_pct_crit", 20)
        results["orphans"] = ("CRIT" if pct > crit else "WARN" if pct > warn else "OK",
                              f"{orphans}/{total} ({pct:.0f}%)")
    else:
        results["orphans"] = ("OK", "No files")
    # Claude Vault
    try:
        r = subprocess.run(['launchctl', 'list'], capture_output=True, text=True, timeout=10)
        results["claude_vault"] = ("OK", "Running") if 'com.claudevault.watch' in r.stdout else ("CRIT", "Not loaded")
    except (subprocess.TimeoutExpired, OSError):
        results["claude_vault"] = ("CRIT", "Cannot check")
    # Topics folder
    td = os.path.join(vp, config["topics_folder"])
    if os.path.isdir(td):
        count = sum(1 for f in os.listdir(td) if f.endswith('.md'))
        results["topics_folder"] = ("OK", f"{count} topic notes") if count > 0 else ("CRIT", "Empty")
    else:
        results["topics_folder"] = ("CRIT", "Missing")
    # Session recency
    age = newest_file_age_days(os.path.join(vp, "Sessions"))
    if age is None:
        results["session_recency"] = ("CRIT", "No files")
    else:
        sw, sc = th.get("session_freshness_warn_days", 7), th.get("session_freshness_crit_days", 14)
        results["session_recency"] = ("CRIT" if age > sc else "WARN" if age > sw else "OK", f"{age:.1f} days")
    # Export recency
    age = newest_file_age_days(os.path.join(vp, "Conversations"))
    if age is None:
        results["export_recency"] = ("CRIT", "No files")
    else:
        ew, ec = th.get("export_freshness_warn_days", 7), th.get("export_freshness_crit_days", 14)
        results["export_recency"] = ("CRIT" if age > ec else "WARN" if age > ew else "OK", f"{age:.1f} days")
    # Topic freshness (info only)
    age = newest_file_age_days(td)
    results["topic_freshness"] = ("INFO", f"{age:.0f} days" if age else "No files")
    # Linker script valid
    script = expand_path("~/claude-vault/topic-linker.py")
    cfg = expand_path("~/.config/topic-linker/config.json")
    if not os.path.exists(script):
        results["linker_script"] = ("CRIT", "Not found")
    elif not os.access(script, os.X_OK):
        results["linker_script"] = ("CRIT", "Not executable")
    else:
        try:
            r = subprocess.run([sys.executable, script, '--config', cfg, '--dry-run'],
                               capture_output=True, text=True, timeout=30)
            results["linker_script"] = ("OK", "Valid") if r.returncode == 0 else ("CRIT", f"--dry-run failed (exit {r.returncode})")
        except (subprocess.TimeoutExpired, OSError) as e:
            results["linker_script"] = ("CRIT", f"Cannot run: {e}")
    return results

def format_health_md(results):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    emoji = {"OK": "\u2705", "WARN": "\u26a0\ufe0f", "CRIT": "\u274c", "INFO": "\u2139\ufe0f"}
    labels = {"linker_recency": "Topic linker", "lockfile": "Lockfile", "orphans": "Cross-folder orphans",
              "claude_vault": "Claude Vault", "topics_folder": "Topics folder", "session_recency": "Session log recency",
              "export_recency": "Export recency", "topic_freshness": "Topic freshness", "linker_script": "Linker script valid"}
    lines = ["---", "tags: [vault-health, auto-generated]", "---", "",
             "# Vault Health Check", "", f"**Last checked:** {now}", "",
             "| Check | Status | Detail |", "|-------|--------|--------|"]
    if "error" in results:
        lines.append(f"| Config | \u274c | {results['error']} |")
    else:
        for k, label in labels.items():
            if k in results:
                s, d = results[k]
                lines.append(f"| {label} | {emoji.get(s, '\u2753')} {s} | {d} |")
    lines.append(f"| Version | \u2139\ufe0f v{VERSION} | Check dontsleeponai.com/obsidian-claude-code for updates |")
    lines.append("")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Vault health check v" + VERSION)
    parser.add_argument('--config', default='~/.config/topic-linker/config.json')
    parser.add_argument('--vault-path', default=None)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    config_path = expand_path(args.config)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            pre = json.load(f)
        log_dir = pre.get("log_dir", "~/claude-vault/")
    except (FileNotFoundError, json.JSONDecodeError):
        log_dir = "~/claude-vault/"
    log_dir = expand_path(log_dir)
    os.makedirs(log_dir, exist_ok=True)
    handlers = [logging.FileHandler(os.path.join(log_dir, "vault-health.log"), encoding='utf-8')]
    if args.dry_run:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(handlers=handlers, level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    logging.info(f"vault-health v{VERSION} starting")
    results = check_vault_health(config_path=args.config, vault_path=args.vault_path)
    md = format_health_md(results)
    if args.dry_run:
        print(md)
    else:
        if "error" not in results:
            try:
                config = load_config(expand_path(args.config))
                out = os.path.join(expand_path(config["vault_path"]), "vault-health.md")
                atomic_write(out, md)
                logging.info(f"Wrote {out}")
            except (ValueError, json.JSONDecodeError):
                print(md)
        else:
            print(md)

if __name__ == '__main__':
    main()
