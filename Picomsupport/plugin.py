#!/usr/bin/env python3
"""
fix_picom_config.py

Usage:
  python3 ~/fix_picom_config.py         # runs in "suggest restore if backup found" mode (non-interactive)
  python3 ~/fix_picom_config.py --restore-latest   # automatically restore latest backup if present
  python3 ~/fix_picom_config.py --sanitize-only    # don't restore, just sanitize file in place (removes leading backslashes)

What it does:
 - Locates ~/.config/picom.conf (and a couple of other candidate paths)
 - Creates a .broken.TIMESTAMP backup of the current file
 - If a plugin-style backup like "picom.conf.bak.TIMESTAMP" is present, restores the newest such backup
 - Else sanitizes file by removing leading backslashes at start-of-line (keeps everything else)
"""
import sys, shutil, re
from pathlib import Path
from datetime import datetime

CANDIDATES = [
    Path.home() / ".config" / "picom.conf",
    Path.home() / ".config" / "pipewire" / "picom.conf",
]

def find_path():
    for p in CANDIDATES:
        if p.exists():
            return p
    # default to primary candidate
    return CANDIDATES[0]

def list_plugin_backups(cfg_path: Path):
    # match pattern like picom.conf.bak.20251113_123456
    pdir = cfg_path.parent
    base = cfg_path.name
    suffix_pat = base + ".bak."
    found = []
    for f in pdir.iterdir():
        if f.is_file() and f.name.startswith(suffix_pat):
            found.append(f)
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found

def make_broken_backup(cfg_path: Path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    broken = cfg_path.with_name(cfg_path.name + f".broken.{ts}")
    shutil.copy2(cfg_path, broken)
    return broken

def restore_backup(cfg_path: Path, backup_path: Path):
    # make a pre-restore broken backup first
    pre = make_broken_backup(cfg_path)
    shutil.copy2(backup_path, cfg_path)
    return pre

def sanitize_remove_leading_backslashes(cfg_path: Path):
    # back up broken file first
    broken = make_broken_backup(cfg_path)
    print(f"Created broken backup: {broken}")
    # remove leading backslashes only at start of line (preserves internal \)
    new_lines = []
    pattern = re.compile(r'^[\\]+(\s*)')  # leading backslashes followed by optional spaces
    with cfg_path.open("r", encoding="utf-8", errors="surrogateescape") as fh:
        for ln in fh:
            # if line starts with backslashes, remove them but preserve indentation after them
            m = pattern.match(ln)
            if m:
                # remove leading backslashes
                rest = ln[m.end():]
                # but if rest begins with "#" that probably means previously escaped comment; keep '#' but remove extra "\" before it
                new_lines.append(rest)
            else:
                new_lines.append(ln)
    # write back
    cfg_path.write_text("".join(new_lines), encoding="utf-8")
    return broken

def main():
    cfg = find_path()
    print("Target picom config:", cfg)
    if not cfg.exists():
        print("Warning: config does not exist yet at that path. Nothing to restore or sanitize.")
        return

    backups = list_plugin_backups(cfg)
    if "--sanitize-only" in sys.argv:
        print("Sanitize-only requested.")
        br = sanitize_remove_leading_backslashes(cfg)
        print("Sanitized file. Created broken backup:", br)
        return

    if "--restore-latest" in sys.argv:
        if backups:
            print("Found plugin-style backups, restoring latest:", backups[0])
            pre = restore_backup(cfg, backups[0])
            print("Restored. Pre-restore broken backup at:", pre)
        else:
            print("No plugin backup found. Sanitizing instead.")
            br = sanitize_remove_leading_backslashes(cfg)
            print("Sanitized file. Created broken backup:", br)
        return

    # default interactive-ish: if backups exist, restore latest, else sanitize
    if backups:
        print("Found plugin-style backups (newest first):")
        for b in backups[:5]:
            print("  ", b)
        # restore newest (non-interactive)
        print("Restoring newest backup:", backups[0])
        pre = restore_backup(cfg, backups[0])
        print("Restored. Pre-restore broken backup at:", pre)
    else:
        print("No plugin-style backups found. Sanitizing file by removing leading backslashes at line starts.")
        br = sanitize_remove_leading_backslashes(cfg)
        print("Sanitized file. Created broken backup:", br)

if __name__ == "__main__":
    main()
