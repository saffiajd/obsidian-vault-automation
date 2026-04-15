#!/usr/bin/env python3
# topic-linker v4.1.0
"""
Self-healing topic linker for Obsidian vaults.
Adds/updates 'See Also' footer blocks with WikiLinks to matching topic notes.
Runs every 10 minutes via LaunchAgent.

Blocker fixes: atomic writes (B1), fcntl.flock (B2), spaces in path (B3),
Python logging (B4), clean exit codes (B5).
High-priority: strip code blocks (H1), mtime precision (H2), config validation (H6).
"""

import argparse, fcntl, json, logging, os, re, sys, tempfile, time

VERSION = "4.1.0"
FOOTER_START = "<!-- topic-linker:start -->"
FOOTER_END = "<!-- topic-linker:end -->"
REQUIRED_CONFIG_KEYS = ["vault_path", "topics_folder", "skip_folders", "lockfile", "mtime_db"]

def expand_path(p):
    return os.path.expandvars(os.path.expanduser(p))

def load_config(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    for key in REQUIRED_CONFIG_KEYS:
        if key not in config:
            raise ValueError(f"Missing required config key: {key}")
    vault = expand_path(config["vault_path"])
    if not os.path.isdir(vault):
        raise ValueError(f"Vault path does not exist: {vault}")
    return config

def setup_logging(log_dir, dry_run=False):
    log_dir = expand_path(log_dir)
    os.makedirs(log_dir, exist_ok=True)
    handlers = [logging.FileHandler(os.path.join(log_dir, "topic-linker.log"), encoding='utf-8')]
    if dry_run:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(handlers=handlers, level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def atomic_write(path, content, mode='text'):
    dir_name = os.path.dirname(path)
    os.makedirs(dir_name, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=dir_name, suffix='.tmp',
                                     delete=False, encoding='utf-8') as f:
        if mode == 'json':
            json.dump(content, f, indent=2, ensure_ascii=False)
        else:
            f.write(content)
        tmp_path = f.name
    os.rename(tmp_path, path)

def acquire_lock(lockfile_path):
    lockfile_path = expand_path(lockfile_path)
    os.makedirs(os.path.dirname(lockfile_path), exist_ok=True)
    fd = open(lockfile_path, 'w')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(str(os.getpid()))
        fd.flush()
        return fd
    except (BlockingIOError, OSError):
        fd.close()
        return None

def release_lock(fd):
    if fd:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
        except OSError:
            pass

def strip_code_blocks(content):
    return re.sub(r'```[\s\S]*?```|~~~~[\s\S]*?~~~~', '', content)

def strip_existing_footer(content):
    return re.compile(r'\n?' + re.escape(FOOTER_START) + r'[\s\S]*?' + re.escape(FOOTER_END) + r'\n?').sub('', content)

def extract_existing_footer(content):
    match = re.compile(re.escape(FOOTER_START) + r'([\s\S]*?)' + re.escape(FOOTER_END)).search(content)
    return match.group(0) if match else None

def build_footer(matched_topics):
    if not matched_topics:
        return ""
    lines = [FOOTER_START, "---", "## See Also"]
    for topic in sorted(matched_topics):
        lines.append(f"- [[{topic}]]")
    lines.append(FOOTER_END)
    return "\n".join(lines)

def process_file(filepath, topics, dry_run=False):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        logging.warning(f"Cannot read {filepath}: {e}")
        return 'skipped'
    content_without_footer = strip_existing_footer(content)
    clean = strip_code_blocks(content_without_footer).lower()
    clean_norm = clean.replace('-', ' ').replace('_', ' ')
    matched = [name for key, name in topics.items() if key in clean or key in clean_norm]
    new_footer = build_footer(matched)
    existing_footer = extract_existing_footer(content)
    if existing_footer == new_footer:
        return 'unchanged'
    if not existing_footer and not new_footer:
        return 'unchanged'
    base = strip_existing_footer(content).rstrip('\n')
    new_content = base + "\n\n" + new_footer + "\n" if new_footer else base + "\n"
    if dry_run:
        logging.info(f"[DRY-RUN] Would update: {filepath} ({len(matched)} topics)")
        return 'updated'
    atomic_write(filepath, new_content)
    logging.info(f"Updated: {filepath} ({len(matched)} topics)")
    return 'updated'

def run(config_path, dry_run=False):
    try:
        config = load_config(config_path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        logging.error(f"Config error: {e}")
        return 1
    vault_path = expand_path(config["vault_path"])
    lock_fd = acquire_lock(config["lockfile"])
    if lock_fd is None:
        logging.info("Another instance running, exiting.")
        return 0
    try:
        skip = config["skip_folders"]
        folders = sorted(e.name for e in os.scandir(vault_path)
                         if e.is_dir(follow_symlinks=False) and e.name not in skip)
        logging.info(f"Discovered {len(folders)} folders: {folders}")
        topics_dir = os.path.join(vault_path, config["topics_folder"])
        topics = {}
        if os.path.isdir(topics_dir):
            for fn in os.listdir(topics_dir):
                if fn.endswith('.md'):
                    name = fn[:-3]
                    topics[name.lower()] = name
        if not topics:
            logging.warning("No topics found — will clean stale footers if any.")
        else:
            logging.info(f"Loaded {len(topics)} topics")
        mtime_path = expand_path(config["mtime_db"])
        try:
            with open(mtime_path, 'r', encoding='utf-8') as f:
                mtime_db = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            mtime_db = {}
        all_files = []
        for folder in folders:
            fp = os.path.join(vault_path, folder)
            if not os.path.isdir(fp):
                continue
            for root, dirs, fnames in os.walk(fp):
                for fn in fnames:
                    if fn.endswith('.md'):
                        all_files.append(os.path.join(root, fn))
        try:
            with os.scandir(vault_path) as entries:
                for e in entries:
                    if e.is_file(follow_symlinks=False) and e.name.endswith('.md'):
                        all_files.append(e.path)
        except OSError:
            pass
        logging.info(f"Found {len(all_files)} markdown files")
        stats = {'updated': 0, 'unchanged': 0, 'skipped': 0}
        new_mtime_db = {}
        for fpath in all_files:
            try:
                cur = f"{os.path.getmtime(fpath):.9f}"
            except OSError:
                continue
            rel = os.path.relpath(fpath, vault_path)
            if mtime_db.get(rel) == cur:
                new_mtime_db[rel] = cur
                stats['unchanged'] += 1
                continue
            result = process_file(fpath, topics, dry_run)
            stats[result] += 1
            if result == 'updated' and not dry_run:
                new_mtime_db[rel] = f"{os.path.getmtime(fpath):.9f}"
            else:
                new_mtime_db[rel] = cur
        if not dry_run:
            atomic_write(mtime_path, new_mtime_db, mode='json')
        logging.info(f"Done: {stats['updated']} updated, {stats['unchanged']} unchanged, {stats['skipped']} skipped")
        return 0
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        return 1
    finally:
        release_lock(lock_fd)

def main():
    parser = argparse.ArgumentParser(description="Obsidian topic linker v" + VERSION)
    parser.add_argument('--config', default='~/.config/topic-linker/config.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    config_path = expand_path(args.config)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            pre = json.load(f)
        log_dir = pre.get("log_dir", "~/claude-vault/")
    except (FileNotFoundError, json.JSONDecodeError):
        log_dir = "~/claude-vault/"
    setup_logging(log_dir, dry_run=args.dry_run)
    logging.info(f"topic-linker v{VERSION} starting (dry_run={args.dry_run})")
    sys.exit(run(config_path, dry_run=args.dry_run))

if __name__ == '__main__':
    main()
