#!/usr/bin/env python3
"""
i3_plugin.py

An EditorWidget plugin for editing i3 configs. Meant to be imported by config_core.
Exposes:
  - EditorWidget(core_configfile: ConfigFile) -> QWidget

If run directly it will open a small test window (requires PyQt6).
"""
from __future__ import annotations
import os, re
from typing import List, Tuple, Optional, Dict
from pathlib import Path
from configparser import ConfigParser

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QLineEdit, QTextEdit, QTabWidget, QMessageBox, QGroupBox, QComboBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

# -------------------------
# Internal parser helpers (lightweight)
# -------------------------
def leading_whitespace(line: str) -> str:
    return line[:len(line) - len(line.lstrip("\t "))]

def strip_comment_state(raw: str) -> Tuple[str, bool]:
    s = raw.lstrip()
    if s.startswith("#"):
        return s[1:].lstrip(), True
    return s, False

def find_bindsym_lines(lines: List[str]) -> List[Tuple[int, str, bool]]:
    out = []
    for i, raw in enumerate(lines):
        inner, commented = strip_comment_state(raw)
        if inner.startswith("bindsym "):
            out.append((i, raw, commented))
    return out

def find_startup_lines(lines: List[str]) -> List[Tuple[int, str, bool]]:
    out = []
    for i, raw in enumerate(lines):
        inner, commented = strip_comment_state(raw)
        low = inner.lower()
        if low.startswith("exec ") or low.startswith("exec_always ") or low.startswith("exec --no-startup-id"):
            out.append((i, raw, commented))
    return out

def parse_bindsym_line(raw: str) -> Dict[str, str]:
    lw = leading_whitespace(raw)
    inner, commented = strip_comment_state(raw)
    parts = inner.split(None, 2)
    cmd = parts[0] if parts else ""
    keys = parts[1] if len(parts) > 1 else ""
    action = parts[2] if len(parts) > 2 else ""
    return {"cmd": cmd, "keys": keys, "action": action, "commented": commented, "leading_ws": lw}

def format_bindsym(cmd: str, keys: str, action: str, commented: bool=False, leading_ws: str="") -> str:
    inner = f"{cmd} {keys} {action}".strip()
    prefix = "# " if commented else ""
    return f"{leading_ws}{prefix}{inner}"

def parse_startup_line(raw: str) -> Dict[str, str]:
    lw = leading_whitespace(raw)
    inner, commented = strip_comment_state(raw)
    if inner.lower().startswith("exec --no-startup-id"):
        prefix = "exec"
        flag = "--no-startup-id"
        cmd = inner[len("exec --no-startup-id"):].lstrip()
    elif inner.lower().startswith("exec_always"):
        prefix = "exec_always"
        flag = ""
        cmd = inner[len("exec_always"):].lstrip()
    elif inner.lower().startswith("exec "):
        prefix = "exec"
        flag = ""
        cmd = inner[len("exec"):].lstrip()
    else:
        prefix = ""
        flag = ""
        cmd = inner
    return {"prefix": prefix, "flag": flag, "command": cmd, "commented": commented, "leading_ws": lw}

def format_startup(prefix: str, flag: str, command: str, commented: bool=False, leading_ws: str="") -> str:
    inner = prefix
    if flag:
        inner += " " + flag
    if command:
        inner += " " + command
    prefix_s = "# " if commented else ""
    return leading_ws + prefix_s + inner

# -------------------------
# .desktop scanning (re-used lightweight)
# -------------------------
DESKTOP_PATHS = [
    "/usr/share/applications",
    "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications"),
]

def clean_exec_field(s: str) -> str:
    return re.sub(r'\s?%[a-zA-Z@]', '', s).strip()

def scan_installed_apps() -> List[dict]:
    apps = []
    seen = set()
    for d in DESKTOP_PATHS:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".desktop"):
                continue
            path = os.path.join(d, fn)
            try:
                cfg = ConfigParser(interpolation=None)
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    txt = f.read()
                cfg.read_string(txt)
                if "Desktop Entry" not in cfg:
                    continue
                ent = cfg["Desktop Entry"]
                if ent.get("NoDisplay", "false").lower() == "true":
                    continue
                name = ent.get("Name") or fn.replace(".desktop", "")
                exec_field = ent.get("Exec") or ""
                exec_field = clean_exec_field(exec_field)
                if not exec_field:
                    continue
                key = (name, exec_field)
                if key in seen:
                    continue
                seen.add(key)
                apps.append({"name": name, "exec": exec_field})
            except Exception:
                continue
    apps.sort(key=lambda x: x["name"].lower())
    return apps

# -------------------------
# EditorWidget
# -------------------------
class EditorWidget(QWidget):
    """
    A simple i3 editor widget that integrates with core.ConfigFile.
    Constructor: EditorWidget(core_configfile: ConfigFile)
    """
    def __init__(self, core_configfile=None):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.core = core_configfile  # may be None in tests
        # if no config provided, try to auto-find
        if self.core is None:
            # try common i3 locations
            cand = [
                os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "i3", "config"),
                os.path.join(os.path.expanduser("~/.config"), "i3", "config"),
                os.path.join(os.path.expanduser("~/.i3"), "config"),
            ]
            cfgpath = None
            for p in cand:
                if os.path.isfile(p):
                    cfgpath = p
                    break
            if cfgpath:
                try:
                    from config_core import ConfigFile as CF
                    self.core = CF(cfgpath)
                except Exception:
                    self.core = None

        header = QHBoxLayout()
        self.layout().addLayout(header)
        title = QLabel("i3 Editor (plugin)")
        title.setFont(QFont("monospace", 12))
        header.addWidget(title)
        header.addStretch()
        save_btn = QPushButton("Save (create backup)")
        save_btn.clicked.connect(self.save)
        header.addWidget(save_btn)

        # tabs: Keybinds, Startup
        self.tabs = QTabWidget()
        self.layout().addWidget(self.tabs)

        self.key_tab = QWidget()
        self.key_tab.setLayout(QVBoxLayout())
        self.tabs.addTab(self.key_tab, "Keybinds")

        self.start_tab = QWidget()
        self.start_tab.setLayout(QVBoxLayout())
        self.tabs.addTab(self.start_tab, "Startup")

        # populate lists
        self.refresh()

    def refresh(self):
        # clear key_tab and start_tab contents
        for i in reversed(range(self.key_tab.layout().count())):
            w = self.key_tab.layout().itemAt(i).widget()
            if w:
                w.setParent(None)
        for i in reversed(range(self.start_tab.layout().count())):
            w = self.start_tab.layout().itemAt(i).widget()
            if w:
                w.setParent(None)

        lines = self.core.lines if self.core else []
        binds = find_bindsym_lines(lines)
        starts = find_startup_lines(lines)

        # Keybinds list
        if not binds:
            self.key_tab.layout().addWidget(QLabel("(no bindsym lines found)"))
        else:
            for idx, raw, commented in binds:
                frame = QFrame()
                frame.setLayout(QHBoxLayout())
                frame.layout().addWidget(QLabel(f"Line {idx+1}:"))
                preview = QLabel(raw.strip())
                preview.setFont(QFont("monospace", 10))
                preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                frame.layout().addWidget(preview, 1)
                edit_btn = QPushButton("Edit")
                edit_btn.clicked.connect(self._make_edit_bindsym(idx, raw, commented))
                frame.layout().addWidget(edit_btn)
                toggle_btn = QPushButton("Toggle comment")
                toggle_btn.clicked.connect(self._make_toggle(idx, raw, commented))
                frame.layout().addWidget(toggle_btn)
                self.key_tab.layout().addWidget(frame)

        # Startup list
        if not starts:
            self.start_tab.layout().addWidget(QLabel("(no startup lines found)"))
        else:
            for idx, raw, commented in starts:
                frame = QFrame()
                frame.setLayout(QHBoxLayout())
                frame.layout().addWidget(QLabel(f"Line {idx+1}:"))
                preview = QLabel(raw.strip())
                preview.setFont(QFont("monospace", 10))
                preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                frame.layout().addWidget(preview, 1)
                edit_btn = QPushButton("Edit")
                edit_btn.clicked.connect(self._make_edit_startup(idx, raw, commented))
                frame.layout().addWidget(edit_btn)
                toggle_btn = QPushButton("Toggle comment")
                toggle_btn.clicked.connect(self._make_toggle(idx, raw, commented))
                frame.layout().addWidget(toggle_btn)
                self.start_tab.layout().addWidget(frame)

    # factories to capture loop variables
    def _make_edit_bindsym(self, idx, raw, commented):
        def fn():
            dlg = EditBindsymSmall(self, idx, raw, commented)
            if dlg.exec():
                new_line = dlg.new_line
                if self.core:
                    self.core.replace_line(idx, new_line)
                self.refresh()
        return fn

    def _make_edit_startup(self, idx, raw, commented):
        def fn():
            dlg = EditStartupSmall(self, idx, raw, commented)
            if dlg.exec():
                new_line = dlg.new_line
                if self.core:
                    self.core.replace_line(idx, new_line)
                self.refresh()
        return fn

    def _make_toggle(self, idx, raw, commented):
        def fn():
            if commented:
                new = uncomment_line(raw)
            else:
                new = comment_line(raw)
            if self.core:
                self.core.replace_line(idx, new)
            self.refresh()
        return fn

    def save(self):
        if not self.core:
            QMessageBox.information(self, "No config", "No config file available.")
            return
        bak = self.core.save()
        QMessageBox.information(self, "Saved", f"Saved. Backup: {bak}")

# -------------------------
# small edit dialogs (lightweight)
# -------------------------
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout

class EditBindsymSmall(QDialog):
    def __init__(self, parent, idx, raw, commented):
        super().__init__(parent)
        self.setWindowTitle("Edit bindsym")
        self.idx = idx
        self.raw = raw
        self.commented = commented
        self.resize(700, 180)

        data = parse_bindsym_line(raw)
        layout = QVBoxLayout()
        self.setLayout(layout)
        info = QLabel(f"Line {idx+1}: {raw.strip()}")
        layout.addWidget(info)

        form = QFormLayout()
        self.keys_edit = QLineEdit(data["keys"])
        form.addRow("Keys:", self.keys_edit)
        self.action_edit = QLineEdit(data["action"])
        form.addRow("Action:", self.action_edit)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview)
        self.update_preview()

        self.keys_edit.textChanged.connect(self.update_preview)
        self.action_edit.textChanged.connect(self.update_preview)

    def update_preview(self):
        k = self.keys_edit.text().strip()
        a = self.action_edit.text().strip()
        if not k:
            self.preview.setPlainText("(invalid: no keys)")
        else:
            self.preview.setPlainText(format_bindsym("bindsym", k, a, self.commented, leading_whitespace(self.raw)))

    def on_accept(self):
        k = self.keys_edit.text().strip()
        a = self.action_edit.text().strip()
        if not k:
            QMessageBox.warning(self, "Invalid", "Keys cannot be empty.")
            return
        self.new_line = format_bindsym("bindsym", k, a, self.commented, leading_whitespace(self.raw))
        self.accept()

class EditStartupSmall(QDialog):
    def __init__(self, parent, idx, raw, commented):
        super().__init__(parent)
        self.setWindowTitle("Edit startup")
        self.idx = idx
        self.raw = raw
        self.commented = commented
        self.resize(700, 180)

        data = parse_startup_line(raw)
        layout = QVBoxLayout()
        self.setLayout(layout)
        info = QLabel(f"Line {idx+1}: {raw.strip()}")
        layout.addWidget(info)

        form = QFormLayout()
        self.prefix_combo = QComboBox()
        self.prefix_combo.addItems(["exec", "exec_always"])
        self.prefix_combo.setCurrentText(data["prefix"] or "exec")
        form.addRow("Prefix:", self.prefix_combo)

        self.flag_combo = QComboBox()
        self.flag_combo.addItems(["", "--no-startup-id"])
        self.flag_combo.setCurrentText(data["flag"] or "")
        form.addRow("Flag:", self.flag_combo)

        self.cmd_edit = QLineEdit(data["command"])
        form.addRow("Command:", self.cmd_edit)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview)
        self.update_preview()
        self.prefix_combo.currentIndexChanged.connect(self.update_preview)
        self.flag_combo.currentIndexChanged.connect(self.update_preview)
        self.cmd_edit.textChanged.connect(self.update_preview)

    def update_preview(self):
        pre = self.prefix_combo.currentText().strip()
        flag = self.flag_combo.currentText().strip()
        cmd = self.cmd_edit.text().strip()
        self.preview.setPlainText(format_startup(pre, flag, cmd, self.commented, leading_whitespace(self.raw)))

    def on_accept(self):
        cmd = self.cmd_edit.text().strip()
        if not cmd:
            QMessageBox.warning(self, "Invalid", "Command cannot be empty.")
            return
        pre = self.prefix_combo.currentText().strip()
        flag = self.flag_combo.currentText().strip()
        self.new_line = format_startup(pre, flag, cmd, self.commented, leading_whitespace(self.raw))
        self.accept()

# -------------------------
# If run standalone, open a test window
# -------------------------
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    from config_core import ConfigFile
    app = QApplication(sys.argv)
    # attempt to load default i3 config
    cfgpath = None
    cand = [
        os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "i3", "config"),
        os.path.join(os.path.expanduser("~/.config"), "i3", "config"),
        os.path.join(os.path.expanduser("~/.i3"), "config"),
    ]
    for p in cand:
        if os.path.isfile(p):
            cfgpath = p
            break
    cf = None
    if cfgpath:
        try:
            cf = ConfigFile(cfgpath)
        except Exception:
            cf = None
    w = EditorWidget(cf)
    w.resize(1000, 700)
    w.show()
    sys.exit(app.exec())
