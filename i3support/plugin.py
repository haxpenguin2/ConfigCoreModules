#!/usr/bin/env python3
"""
i3_plugin plugin.py

i3 editor plugin that matches the behavior of the working editor:
- Edit bindsym lines (split key capture fields, modifiers included)
- Edit startup lines (prefix, flag, app chooser)
- Searchable app dropdown from .desktop
- Uses config_core.ConfigFile for staging & saving (backups)
- Exposes EditorWidget(core_config: ConfigFile)
"""
from __future__ import annotations
import os, re, traceback
from typing import List, Tuple, Optional, Dict
from pathlib import Path
from configparser import ConfigParser

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QLineEdit, QTextEdit, QTabWidget, QMessageBox, QGroupBox,
    QComboBox, QDialog, QGridLayout, QDialogButtonBox, QFormLayout, QListWidget, QSizePolicy, QCompleter
)
from PyQt6.QtGui import QFont, QKeySequence, QIcon
from PyQt6.QtCore import Qt, QStringListModel

# -------------------------
# Helpers: parsing/formatting (same logic as working editor)
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

def parse_bindsym_line(raw: str) -> Dict[str, Optional[str]]:
    lw = leading_whitespace(raw)
    s = raw.lstrip()
    commented = s.startswith("#")
    inner = s[1:].lstrip() if commented else s
    parts = inner.split(None, 2)
    cmd = parts[0] if parts else ""
    keys = parts[1] if len(parts) >= 2 else ""
    action = parts[2] if len(parts) >= 3 else ""
    return {"cmd": cmd, "keys": keys, "action": action, "commented": commented, "leading_ws": lw}

def format_bindsym(cmd: str, keys: str, action: str, commented: bool=False, leading_ws: str="") -> str:
    inner = f"{cmd} {keys} {action}".strip()
    prefix = "# " if commented else ""
    return f"{leading_ws}{prefix}{inner}"

def parse_startup_line(raw: str) -> Dict[str, Optional[str]]:
    lw = leading_whitespace(raw)
    s = raw.lstrip()
    commented = s.startswith("#")
    inner = s[1:].lstrip() if commented else s
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
        prefix = ""
        flag = ""
        command = inner
    return {"prefix": prefix, "flag": flag, "command": command, "commented": commented, "leading_ws": lw}

def format_startup(prefix: str, flag: str, command: str, commented: bool=False, leading_ws: str="") -> str:
    inner = prefix
    if flag:
        inner += " " + flag
    if command:
        inner += " " + command
    prefix_s = "# " if commented else ""
    return f"{leading_ws}{prefix_s}{inner}"

# -------------------------
# Desktop scanning (searchable app list)
# -------------------------
DESKTOP_PATHS = [
    "/usr/share/applications",
    "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications")
]

def _clean_exec_field(exec_field: str) -> str:
    return re.sub(r'\s?%[a-zA-Z@]', '', exec_field).strip()

def scan_installed_apps() -> List[dict]:
    apps = []
    seen = set()
    for base in DESKTOP_PATHS:
        if not os.path.isdir(base):
            continue
        for fn in os.listdir(base):
            if not fn.endswith(".desktop"):
                continue
            full = os.path.join(base, fn)
            try:
                cfg = ConfigParser(interpolation=None)
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    txt = f.read()
                cfg.read_string(txt)
                if "Desktop Entry" not in cfg:
                    continue
                ent = cfg["Desktop Entry"]
                if ent.get("NoDisplay", "false").lower() == "true":
                    continue
                name = ent.get("Name") or fn.replace(".desktop", "")
                exec_field = ent.get("Exec") or ""
                exec_field = _clean_exec_field(exec_field)
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
# Key capture normalization (modifier-only detection)
# -------------------------
def key_event_to_string(event) -> str:
    mods = []
    m = event.modifiers()
    if m & Qt.KeyboardModifier.ControlModifier:
        mods.append("Control")
    if m & Qt.KeyboardModifier.ShiftModifier:
        mods.append("Shift")
    if m & Qt.KeyboardModifier.AltModifier:
        mods.append("Alt")
    if m & Qt.KeyboardModifier.MetaModifier:
        mods.append("Super")
    key = event.key()
    # pure modifiers
    if key == Qt.Key.Key_Control:
        return "Control"
    if key == Qt.Key.Key_Shift:
        return "Shift"
    if key == Qt.Key.Key_Alt:
        return "Alt"
    if key == Qt.Key.Key_Meta:
        return "Super"
    try:
        seq = QKeySequence(int(m) | key)
        s = seq.toString()
    except Exception:
        s = ""
    if s:
        s = s.replace("Ctrl", "Control").replace("Meta", "Super")
        s = s.replace(" ", "")
        return s
    t = event.text()
    if t:
        tval = t.upper() if t.isalpha() else t
        if mods:
            return "+".join(mods + [tval])
        return tval
    return f"Key({key})"

# -------------------------
# UI widgets used by the plugin
# -------------------------
from PyQt6.QtWidgets import QLineEdit
class KeyCaptureLineEdit(QLineEdit):
    def __init__(self, initial: str = "", parent=None):
        super().__init__(parent)
        self.setText(initial)
        self.setPlaceholderText("Click and press combo (or type)")
        self.setFont(QFont("monospace", 10))
    def keyPressEvent(self, event):
        combo = key_event_to_string(event)
        if combo:
            self.setText(combo)
        event.accept()

class AppComboBox(QComboBox):
    def __init__(self, apps: List[dict], parent=None):
        super().__init__(parent)
        self.apps = apps
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.populate()
        comp = QCompleter([f"{a['name']} — {a['exec']}" for a in apps])
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCompleter(comp)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
    def populate(self):
        self.clear()
        for a in self.apps:
            display = f"{a['name']} — {a['exec']}"
            self.addItem(display, a['exec'])
    def current_exec(self) -> str:
        idx = self.currentIndex()
        if idx >= 0:
            data = self.itemData(idx)
            if data:
                return data
        txt = self.currentText().strip()
        if ' — ' in txt:
            return txt.split(' — ', 1)[1].strip()
        return txt

# -------------------------
# Small dialogs for editing bindsym & startup (feature-parity)
# -------------------------
class EditBindsymDialog(QDialog):
    def __init__(self, parent, index: Optional[int], raw_line: str, commented: bool, apps: List[dict], new_entry: bool=False):
        super().__init__(parent)
        self.setWindowTitle("Edit Keybind" if not new_entry else "Add Keybind")
        self.resize(860, 260)
        self.index = index
        self.raw_line = raw_line
        self.commented = commented
        self.new_entry = new_entry
        self.apps = apps
        if raw_line and not new_entry:
            info = parse_bindsym_line(raw_line)
            self.cmd = info["cmd"]
            self.keys = info["keys"]
            self.action = info["action"]
        else:
            self.cmd = "bindsym"
            self.keys = "$mod+Return"
            self.action = "exec i3-sensible-terminal"
        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(QLabel(f"{'New' if new_entry else f'Line {index+1}'}: {raw_line.strip() if raw_line else '(new)'}"))
        # keys area (split)
        keys_box = QGroupBox("Keys (split by '+') — click field and press combo; right-click to type")
        kbox_layout = QHBoxLayout()
        keys_box.setLayout(kbox_layout)
        self.key_fields: List[KeyCaptureLineEdit] = []
        for frag in self.keys.split("+"):
            fld = KeyCaptureLineEdit(frag, self)
            fld.setFixedWidth(180)
            self.key_fields.append(fld)
            kbox_layout.addWidget(fld)
        kbox_layout.addStretch()
        layout.addWidget(keys_box)
        # action chooser
        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("Action type:"))
        self.action_type = QComboBox()
        self.action_type.addItems(["exec", "custom"])
        action_row.addWidget(self.action_type)
        self.app_combo = AppComboBox(self.apps)
        self.app_combo.setFixedWidth(420)
        action_row.addWidget(self.app_combo)
        layout.addLayout(action_row)
        self.action_edit = QLineEdit(self.action)
        self.action_edit.setFont(QFont("monospace", 10))
        layout.addWidget(self.action_edit)
        # wiring
        def on_action_type(i):
            t = self.action_type.currentText()
            if t == "exec":
                self.app_combo.show()
                if self.app_combo.current_exec():
                    self.action_edit.setText("exec " + self.app_combo.current_exec())
            else:
                self.app_combo.hide()
        self.action_type.currentIndexChanged.connect(on_action_type)
        on_action_type(self.action_type.currentIndex())
        def on_app(i):
            if self.action_type.currentText() == "exec":
                cmd = self.app_combo.current_exec()
                if cmd:
                    self.action_edit.setText("exec " + cmd)
        self.app_combo.currentIndexChanged.connect(on_app)
        # preview + buttons
        btn_row = QHBoxLayout()
        preview_btn = QPushButton("Preview")
        preview_btn.clicked.connect(self.preview)
        btn_row.addWidget(preview_btn)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.apply)
        btn_row.addWidget(apply_btn)
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)
        self.preview_area = QTextEdit()
        self.preview_area.setReadOnly(True)
        self.preview_area.setFixedHeight(100)
        layout.addWidget(self.preview_area)
        self.preview()
    def preview(self):
        new_keys = "+".join(f.text().strip() for f in self.key_fields if f.text().strip()!="")
        act = self.action_edit.text().strip()
        if not new_keys:
            self.preview_area.setPlainText("(invalid: no keys)")
            return ""
        preview_line = f"{self.cmd} {new_keys} {act}".strip()
        lw = self.raw_line[:len(self.raw_line)-len(self.raw_line.lstrip("\t "))] if self.raw_line and not self.new_entry else ""
        preview_line = lw + ("# " if self.commented else "") + preview_line
        self.preview_area.setPlainText(preview_line)
        return preview_line
    def apply(self):
        new_line = self.preview()
        if not new_line:
            QMessageBox.warning(self, "Invalid", "Please specify keys")
            return
        self.new_line = new_line
        self.accept()

class EditStartupDialog(QDialog):
    def __init__(self, parent, index: Optional[int], raw_line: str, commented: bool, apps: List[dict], new_entry: bool=False):
        super().__init__(parent)
        self.setWindowTitle("Edit Startup" if not new_entry else "Add Startup App")
        self.resize(760, 200)
        self.index = index
        self.raw_line = raw_line
        self.commented = commented
        self.new_entry = new_entry
        self.apps = apps
        if raw_line and not new_entry:
            info = parse_startup_line(raw_line)
            self.base = info["prefix"] or "exec"
            self.flag = info["flag"] or ""
            self.rest = info["command"] or ""
        else:
            self.base = "exec"
            self.flag = ""
            self.rest = ""
        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(QLabel(f"{'New' if new_entry else f'Line {index+1}'}: {raw_line.strip() if raw_line else '(new)'}"))
        grid = QGridLayout()
        layout.addLayout(grid)
        grid.addWidget(QLabel("Prefix:"), 0, 0)
        self.prefix = QComboBox()
        self.prefix.addItems(["exec", "exec_always"])
        self.prefix.setCurrentText(self.base)
        grid.addWidget(self.prefix, 0, 1)
        grid.addWidget(QLabel("Flag:"), 0, 2)
        self.flag_combo = QComboBox()
        self.flag_combo.addItems(["", "--no-startup-id"])
        self.flag_combo.setCurrentText(self.flag)
        grid.addWidget(self.flag_combo, 0, 3)
        grid.addWidget(QLabel("App/Command:"), 1, 0)
        self.app_combo = AppComboBox(self.apps)
        self.app_combo.setFixedWidth(520)
        if self.rest:
            # try select
            found = False
            for i in range(self.app_combo.count()):
                if self.app_combo.itemData(i) and self.app_combo.itemData(i).strip() == self.rest.strip():
                    self.app_combo.setCurrentIndex(i)
                    found = True
                    break
            if not found:
                self.app_combo.setEditText(self.rest)
        grid.addWidget(self.app_combo, 1, 1, 1, 3)
        # buttons + preview
        row = QHBoxLayout()
        preview_btn = QPushButton("Preview")
        preview_btn.clicked.connect(self.preview)
        row.addWidget(preview_btn)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.apply)
        row.addWidget(apply_btn)
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)
        self.preview_area = QTextEdit()
        self.preview_area.setReadOnly(True)
        self.preview_area.setFixedHeight(90)
        layout.addWidget(self.preview_area)
        self.preview()
    def preview(self):
        pre = self.prefix.currentText().strip()
        flag = self.flag_combo.currentText().strip()
        cmd = self.app_combo.current_exec().strip()
        inner = pre
        if flag:
            inner += " " + flag
        if cmd:
            inner += " " + cmd
        lw = self.raw_line[:len(self.raw_line)-len(self.raw_line.lstrip("\t "))] if self.raw_line and not self.new_entry else ""
        preview_line = lw + ("# " if self.commented else "") + inner
        self.preview_area.setPlainText(preview_line)
        return preview_line
    def apply(self):
        if not self.app_combo.current_exec().strip():
            QMessageBox.warning(self, "Invalid", "Command cannot be empty.")
            return
        self.new_line = self.preview()
        self.accept()

# -------------------------
# EditorWidget (exposed to core)
# -------------------------
class EditorWidget(QWidget):
    def __init__(self, core_config=None):
        super().__init__()
        self.core = core_config  # core.ConfigFile instance
        self.setLayout(QVBoxLayout())
        header = QHBoxLayout()
        self.layout().addLayout(header)
        title = QLabel("i3 Editor")
        title.setFont(QFont("monospace", 12))
        header.addWidget(title)
        header.addStretch()
        save_btn = QPushButton("Save (create backup)")
        save_btn.clicked.connect(self.on_save)
        header.addWidget(save_btn)
        # tabs
        self.tabs = QTabWidget()
        self.layout().addWidget(self.tabs)
        # Keybinds tab
        self.bind_tab = QWidget()
        self.bind_tab.setLayout(QVBoxLayout())
        self.bind_scroll = QScrollArea()
        self.bind_scroll.setWidgetResizable(True)
        self.bind_container = QWidget()
        self.bind_vbox = QVBoxLayout()
        self.bind_container.setLayout(self.bind_vbox)
        self.bind_scroll.setWidget(self.bind_container)
        self.bind_tab.layout().addWidget(self.bind_scroll)
        add_bind_btn = QPushButton("Add Keybind")
        add_bind_btn.clicked.connect(self.add_keybind)
        self.bind_tab.layout().addWidget(add_bind_btn)
        self.tabs.addTab(self.bind_tab, "Keybinds")
        # Startup tab
        self.start_tab = QWidget()
        self.start_tab.setLayout(QVBoxLayout())
        self.start_scroll = QScrollArea()
        self.start_scroll.setWidgetResizable(True)
        self.start_container = QWidget()
        self.start_vbox = QVBoxLayout()
        self.start_container.setLayout(self.start_vbox)
        self.start_scroll.setWidget(self.start_container)
        self.start_tab.layout().addWidget(self.start_scroll)
        add_start_btn = QPushButton("Add Startup App")
        add_start_btn.clicked.connect(self.add_startup)
        self.start_tab.layout().addWidget(add_start_btn)
        self.tabs.addTab(self.start_tab, "Startup apps")
        # load apps list and refresh UI
        self.apps = scan_installed_apps()
        self.refresh()

    def refresh(self):
        # read lines from core.ConfigFile
        lines = self.core.lines if self.core else []
        binds = find_bindsym_lines(lines)
        starts = find_startup_lines(lines)
        # clear vboxes
        while self.bind_vbox.count():
            w = self.bind_vbox.takeAt(0).widget()
            if w:
                w.deleteLater()
        while self.start_vbox.count():
            w = self.start_vbox.takeAt(0).widget()
            if w:
                w.deleteLater()
        # populate binds
        if not binds:
            self.bind_vbox.addWidget(QLabel("(no bindsym lines found)"))
        else:
            for idx, raw, commented in binds:
                frame = QFrame()
                frame.setLayout(QHBoxLayout())
                frame.layout().addWidget(QLabel(f"Line {idx+1}:"))
                preview = QLabel(raw.strip())
                preview.setFont(QFont("monospace", 10))
                preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                frame.layout().addWidget(preview, 1)
                edit_btn = QPushButton("Edit")
                edit_btn.clicked.connect(self._make_edit_bindsym(idx, raw, commented))
                frame.layout().addWidget(edit_btn)
                toggle_btn = QPushButton("Toggle comment")
                toggle_btn.clicked.connect(self._make_toggle(idx, raw, commented))
                frame.layout().addWidget(toggle_btn)
                preview_btn = QPushButton("Preview")
                preview_btn.clicked.connect(lambda r=raw: QMessageBox.information(self, "Preview", r))
                frame.layout().addWidget(preview_btn)
                self.bind_vbox.addWidget(frame)
        self.bind_vbox.addStretch()
        # populate startup
        if not starts:
            self.start_vbox.addWidget(QLabel("(no startup lines found)"))
        else:
            for idx, raw, commented in starts:
                frame = QFrame()
                frame.setLayout(QHBoxLayout())
                frame.layout().addWidget(QLabel(f"Line {idx+1}:"))
                preview = QLabel(raw.strip())
                preview.setFont(QFont("monospace", 10))
                preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                frame.layout().addWidget(preview, 1)
                edit_btn = QPushButton("Edit")
                edit_btn.clicked.connect(self._make_edit_startup(idx, raw, commented))
                frame.layout().addWidget(edit_btn)
                toggle_btn = QPushButton("Toggle comment")
                toggle_btn.clicked.connect(self._make_toggle(idx, raw, commented))
                frame.layout().addWidget(toggle_btn)
                preview_btn = QPushButton("Preview")
                preview_btn.clicked.connect(lambda r=raw: QMessageBox.information(self, "Preview", r))
                frame.layout().addWidget(preview_btn)
                self.start_vbox.addWidget(frame)
        self.start_vbox.addStretch()

    # factories to capture loop variables
    def _make_edit_bindsym(self, idx, raw, commented):
        def fn():
            dlg = EditBindsymDialog(self, idx, raw, commented, self.apps, new_entry=False)
            if dlg.exec():
                new_line = dlg.new_line
                try:
                    self.core.replace_line(idx, new_line)
                except Exception as e:
                    QMessageBox.critical(self, "Replace failed", str(e))
                self.refresh()
        return fn

    def _make_edit_startup(self, idx, raw, commented):
        def fn():
            dlg = EditStartupDialog(self, idx, raw, commented, self.apps, new_entry=False)
            if dlg.exec():
                new_line = dlg.new_line
                try:
                    self.core.replace_line(idx, new_line)
                except Exception as e:
                    QMessageBox.critical(self, "Replace failed", str(e))
                self.refresh()
        return fn

    def _make_toggle(self, idx, raw, commented):
        def fn():
            try:
                if commented:
                    new = raw[:raw.find('#')] + raw[raw.find('#')+1:] if '#' in raw else raw
                else:
                    lw = leading_whitespace(raw)
                    new = lw + "#" + raw[len(lw):]
                self.core.replace_line(idx, new)
            except Exception as e:
                QMessageBox.critical(self, "Toggle failed", str(e))
            self.refresh()
        return fn

    def add_keybind(self):
        dlg = EditBindsymDialog(self, None, "", False, self.apps, new_entry=True)
        if dlg.exec():
            self.core.append_line(dlg.new_line)
            self.refresh()

    def add_startup(self):
        dlg = EditStartupDialog(self, None, "", False, self.apps, new_entry=True)
        if dlg.exec():
            self.core.append_line(dlg.new_line)
            self.refresh()

    def on_save(self):
        if not self.core:
            QMessageBox.information(self, "No config", "No config file available.")
            return
        try:
            bak = self.core.save()
            QMessageBox.information(self, "Saved", f"Saved config. Backup: {bak}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

# Expose EditorWidget for core loader
# (core expects EditorWidget or create_editor)
# usage: widget = EditorWidget(core.ConfigFile)
