#!/usr/bin/env python3
"""
i3_parser.py

i3-specific parser/formatter that uses config_core.ConfigFile.

Exports:
 - find_bindsym_lines(lines) -> List[(index, raw_line, commented)]
 - find_startup_lines(lines) -> List[(index, raw_line, commented)]
 - parse_bindsym_line(raw_line) -> dict with keys (cmd, keys, action, commented, leading_ws)
 - format_bindsym(cmd, keys, action, commented=False, leading_ws="") -> str
 - parse_startup_line(raw_line) -> dict (prefix, flag, command, commented, leading_ws)
 - format_startup(prefix, flag, command, commented=False, leading_ws="") -> str
 - scan_installed_apps() -> list of dict {name, exec, icon, path}
"""

from __future__ import annotations
import re
import os
from typing import List, Tuple, Optional, Dict
from configparser import ConfigParser
from pathlib import Path

# import core primitives
from config_core import leading_whitespace, is_commented

# -------------------------
# simple finders
# -------------------------
def _strip_comment_state(raw: str) -> Tuple[str, bool]:
    s = raw.lstrip()
    if s.startswith("#"):
        return s[1:].lstrip(), True
    return s, False


def find_bindsym_lines(lines: List[str]) -> List[Tuple[int, str, bool]]:
    """
    Return (index, raw_line, commented) for lines that (after stripping leading
    whitespace and an optional '#') start with 'bindsym '.
    """
    out = []
    for i, raw in enumerate(lines):
        stripped, commented = _strip_comment_state(raw)
        if stripped.startswith("bindsym "):
            out.append((i, raw, commented))
    return out


def find_startup_lines(lines: List[str]) -> List[Tuple[int, str, bool]]:
    """
    Detect lines starting with exec, exec_always, or exec --no-startup-id (optionally commented).
    """
    out = []
    for i, raw in enumerate(lines):
        stripped, commented = _strip_comment_state(raw)
        low = stripped.lower()
        if low.startswith("exec ") or low.startswith("exec_always ") or low.startswith("exec --no-startup-id"):
            out.append((i, raw, commented))
    return out

# -------------------------
# bindsym parse/format
# -------------------------
def parse_bindsym_line(raw_line: str) -> Dict[str, Optional[str]]:
    """
    Parse a bindsym raw line and return a dict:
      { cmd: 'bindsym', keys: '$mod+Shift+Return', action: 'exec firefox', commented: bool, leading_ws: str }

    If parsing fails, returned fields may be empty strings but commented/leading_ws will be present.
    """
    lw = leading_whitespace(raw_line)
    s = raw_line.lstrip()
    commented = s.startswith("#")
    inner = s[1:].lstrip() if commented else s
    parts = inner.split(None, 2)
    cmd = parts[0] if parts else ""
    keys = parts[1] if len(parts) >= 2 else ""
    action = parts[2] if len(parts) >= 3 else ""
    return {
        "cmd": cmd,
        "keys": keys,
        "action": action,
        "commented": commented,
        "leading_ws": lw,
    }


def format_bindsym(cmd: str, keys: str, action: str, commented: bool=False, leading_ws: str="") -> str:
    inner = f"{cmd} {keys} {action}".strip()
    prefix = "# " if commented else ""
    return f"{leading_ws}{prefix}{inner}"


# -------------------------
# startup parse/format
# -------------------------
def parse_startup_line(raw_line: str) -> Dict[str, Optional[str]]:
    """
    Extract prefix, optional flag, and the command part.
    Example lines:
      exec --no-startup-id nm-applet
      exec_always firefox
      exec feh --bg-scale background.png
    Returns dict with keys: prefix ('exec' or 'exec_always'), flag ('' or '--no-startup-id'), command,
    commented (bool), leading_ws.
    """
    lw = leading_whitespace(raw_line)
    s = raw_line.lstrip()
    commented = s.startswith("#")
    inner = s[1:].lstrip() if commented else s
    # match patterns
    # try exec --no-startup-id
    if inner.lower().startswith("exec --no-startup-id"):
        prefix = "exec"
        flag = "--no-startup-id"
        command = inner[len("exec --no-startup-id"):].lstrip()
    elif inner.lower().startswith("exec_always"):
        prefix = "exec_always"
        flag = ""
        command = inner[len("exec_always"):].lstrip()
    elif inner.lower().startswith("exec "):
        prefix = "exec"
        flag = ""
        command = inner[len("exec"):].lstrip()
    else:
        # fallback: treat full inner as command, prefix unknown
        prefix = ""
        flag = ""
        command = inner
    return {
        "prefix": prefix,
        "flag": flag,
        "command": command,
        "commented": commented,
        "leading_ws": lw,
    }


def format_startup(prefix: str, flag: str, command: str, commented: bool=False, leading_ws: str="") -> str:
    if flag:
        inner = f"{prefix} {flag} {command}".strip()
    else:
        inner = f"{prefix} {command}".strip()
    prefix_str = "# " if commented else ""
    return f"{leading_ws}{prefix_str}{inner}"


# -------------------------
# .desktop scanning for exec apps
# -------------------------
DESKTOP_PATHS = [
    "/usr/share/applications",
    "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications"),
]


def _clean_exec_field(exec_field: str) -> str:
    # Remove known field codes like %u %U %f %F %i %c %k and multiple spaces
    return re.sub(r'\s?%[a-zA-Z@]', '', exec_field).strip()


def _parse_desktop(path: str) -> Optional[Dict[str, str]]:
    try:
        cfg = ConfigParser(interpolation=None)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        cfg.read_string(text)
        if "Desktop Entry" not in cfg:
            return None
        ent = cfg["Desktop Entry"]
        if ent.get("NoDisplay", "false").lower() == "true":
            return None
        name = ent.get("Name") or Path(path).stem
        exec_field = ent.get("Exec") or ""
        exec_field = _clean_exec_field(exec_field)
        icon = ent.get("Icon", "")
        if not exec_field:
            return None
        return {"name": name, "exec": exec_field, "icon": icon, "path": path}
    except Exception:
        return None


def scan_installed_apps() -> List[Dict[str, str]]:
    apps = []
    seen = set()
    for base in DESKTOP_PATHS:
        if not os.path.isdir(base):
            continue
        for fn in os.listdir(base):
            if not fn.endswith(".desktop"):
                continue
            full = os.path.join(base, fn)
            parsed = _parse_desktop(full)
            if not parsed:
                continue
            key = (parsed["name"], parsed["exec"])
            if key in seen:
                continue
            seen.add(key)
            apps.append(parsed)
    apps.sort(key=lambda x: x["name"].lower())
    return apps


# -------------------------
# small demo when run directly
# -------------------------
if __name__ == "__main__":
    import argparse
    from config_core import ConfigFile
    parser = argparse.ArgumentParser(description="i3_parser demo: locate bindsym and startup lines")
    parser.add_argument("config", nargs="?", help="path to i3 config (optional - tries common locations)")
    args = parser.parse_args()
    # auto-locate if not provided
    candidate = args.config
    if not candidate:
        possible = [
            os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "i3", "config"),
            os.path.join(os.path.expanduser("~/.config"), "i3", "config"),
            os.path.join(os.path.expanduser("~/.i3"), "config"),
        ]
        for p in possible:
            if os.path.isfile(p):
                candidate = p
                break
    if not candidate:
        raise SystemExit("No config provided and none found in standard locations.")
    cfg = ConfigFile(candidate)
    print(f"Loaded {cfg.line_count()} lines from {cfg.path}\n")

    binds = find_bindsym_lines(cfg.lines)
    print(f"Found {len(binds)} bindsym lines (first 10 shown):")
    for i, raw, commented in binds[:10]:
        info = parse_bindsym_line(raw)
        print(f"  line {i+1}: commented={commented} keys={info['keys']} action={info['action']}")

    starts = find_startup_lines(cfg.lines)
    print(f"\nFound {len(starts)} startup lines (first 10 shown):")
    for i, raw, commented in starts[:10]:
        info = parse_startup_line(raw)
        print(f"  line {i+1}: commented={commented} prefix={info['prefix']} flag={info['flag']} cmd={info['command']}")

    print("\nScanning .desktop apps (first 20):")
    apps = scan_installed_apps()
    for a in apps[:20]:
        print(f"  {a['name']} -> {a['exec']}")
