# plugin.py
# BashSupport plugin — Startup Apps / Appearance / Misc editor for ~/.bashrc
# Compatible with your GUI core: EditorWidget(core_config=None) signature.

import os
import shutil
from pathlib import Path
import re

# Try PyQt6 then PyQt5
try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
        QPushButton, QCheckBox, QSpinBox, QTabWidget, QListWidget, QListWidgetItem,
        QMessageBox
    )
    from PyQt6.QtCore import Qt
except Exception:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
        QPushButton, QCheckBox, QSpinBox, QTabWidget, QListWidget, QListWidgetItem,
        QMessageBox
    )
    from PyQt5.QtCore import Qt

# Regex helpers
ASSIGN_RE = re.compile(r'^(?P<prefix>export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<val>.+)$')
SHOPT_RE = re.compile(r'^\s*shopt\s+(-s|-u)?\s*(?P<opt>\w+)\s*$')
ALIAS_RE = re.compile(r'^\s*alias\s+(?P<key>[\w\-]+)=(?P<val>.+)$')
FUNCTION_START_RE = re.compile(r'^\s*(?:(?:function\s+\w+)|(?:\w+\s*\(\s*\)))\s*\{')
FUNCTION_END_RE = re.compile(r'^\s*\}')
SETOPT_RE = re.compile(r'^\s*set\s+-o\s+(?P<opt>\w+)\s+(?P<val>\w+)\s*$')

def list_path_executables(limit=1000):
    """Return a sorted list of executable names found in $PATH (unique)."""
    exes = []
    paths = os.environ.get("PATH", "").split(os.pathsep)
    seen = set()
    for d in paths:
        if not d:
            continue
        try:
            for name in os.listdir(d):
                if name in seen:
                    continue
                p = Path(d) / name
                if p.is_file() and os.access(p, os.X_OK):
                    exes.append(name)
                    seen.add(name)
        except Exception:
            continue
    exes.sort()
    return exes[:limit]

class EditorWidget(QWidget):
    """
    Constructor: EditorWidget(core_config=None)
    core_config: optional object from the core. If provided and contains `.lines` and `.save(...)`,
                 the plugin will prefer using that (and call core_config.save(backup=True)).
                 Otherwise it edits ~/.bashrc directly.
    """
    def __init__(self, core_config=None):
        super().__init__()
        self.core_config = core_config
        self.bashrc_path = Path.home() / ".bashrc"
        self.using_core = False
        self.lines = []
        self.entries = {}  # mapping of keys to {line_idx, value, kind}
        self.startup_cmds = []  # list of (line_idx, text)
        self._load_source()
        # UI will be constructed now (core is expected to create QApplication first)
        self._build_ui()

    # -----------------------------
    # File parsing & helpers
    # -----------------------------
    def _load_source(self):
        # prefer core lines if provided
        if self.core_config is not None and hasattr(self.core_config, "lines"):
            self.using_core = True
            try:
                self.lines = list(self.core_config.lines)
            except Exception:
                self.using_core = False

        if not self.using_core:
            if self.bashrc_path.exists():
                self.lines = self.bashrc_path.read_text(encoding="utf-8").splitlines(True)  # keep newline chars
            else:
                self.lines = []

        self._parse_lines()

    def _parse_lines(self):
        self.entries = {}
        self.startup_cmds = []
        in_function = False
        for idx, raw in enumerate(self.lines):
            s = raw.strip()
            # function block detection
            if FUNCTION_START_RE.match(s):
                in_function = True
            if in_function:
                if FUNCTION_END_RE.match(s):
                    in_function = False
                continue

            if not s or s.startswith("#"):
                continue

            # assignment
            m = ASSIGN_RE.match(s)
            if m:
                key = m.group("key")
                val = m.group("val").strip()
                prefix = m.group("prefix") or ""
                self.entries[key] = {"line_idx": idx, "kind": "assign", "prefix": prefix, "val": val}
                continue

            # shopt
            m2 = SHOPT_RE.match(s)
            if m2:
                opt = m2.group("opt")
                # record whether set -s (enable) vs -u (disable) - we treat presence as enabled
                self.entries[f"shopt:{opt}"] = {"line_idx": idx, "kind": "shopt", "text": s}
                continue

            # set -o
            m3 = SETOPT_RE.match(s)
            if m3:
                opt = m3.group("opt")
                val = m3.group("val")
                self.entries[f"setopt:{opt}"] = {"line_idx": idx, "kind": "setopt", "val": val}
                continue

            # alias
            ma = ALIAS_RE.match(s)
            if ma:
                key = ma.group("key")
                val = ma.group("val")
                self.entries[f"alias:{key}"] = {"line_idx": idx, "kind": "alias", "val": val}
                continue

            # fallback: treat as a startup command if it's a simple command (no =, no ;, not 'if' 'case' 'for' etc)
            if ("=" not in s) and (s.find(";") == -1) and (not s.startswith("if ")) and (not s.startswith("case ")) and (not s.startswith("for ")) and (not s.startswith("while ")) and (not s.startswith("function ")):
                # treat as startup command
                self.startup_cmds.append((idx, raw.rstrip("\n")))
                continue

    def _backup(self):
        target = None
        if self.using_core and hasattr(self.core_config, "path"):
            target = Path(self.core_config.path)
        if target is None:
            target = self.bashrc_path
        if target.exists():
            bak = target.parent / (target.name + ".bak")
            shutil.copy(target, bak)

    # -----------------------------
    # UI building
    # -----------------------------
    def _build_ui(self):
        root = QVBoxLayout()
        self.setLayout(root)

        tabs = QTabWidget()
        root.addWidget(tabs)

        # Startup Apps tab
        tabs.addTab(self._build_startup_tab(), "Startup apps")

        # Appearance tab
        tabs.addTab(self._build_appearance_tab(), "Appearance")

        # Misc tab
        tabs.addTab(self._build_misc_tab(), "Misc")

        # Save row
        row = QHBoxLayout()
        save_btn = QPushButton("Save changes")
        save_btn.clicked.connect(self._on_save)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._on_refresh)
        row.addWidget(save_btn)
        row.addWidget(refresh_btn)
        root.addLayout(row)

    # -----------------------------
    # Startup tab
    # -----------------------------
    def _build_startup_tab(self):
        w = QWidget()
        layout = QVBoxLayout()
        w.setLayout(layout)

        layout.addWidget(QLabel("Detected startup commands (simple, not inside functions):"))
        self.startup_list = QListWidget()
        for idx, txt in self.startup_cmds:
            item = QListWidgetItem(txt)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.startup_list.addItem(item)
        layout.addWidget(self.startup_list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add command")
        add_btn.clicked.connect(self._on_add_startup)
        rm_btn = QPushButton("Remove selected")
        rm_btn.clicked.connect(self._on_remove_startup)
        edit_btn = QPushButton("Edit selected")
        edit_btn.clicked.connect(self._on_edit_startup)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(rm_btn)
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("Quick pick installed executable (searchable):"))
        self.exec_combo = QComboBox()
        self.exec_combo.setEditable(True)  # allow search typing
        for exe in list_path_executables():
            self.exec_combo.addItem(exe)
        layout.addWidget(self.exec_combo)

        run_row = QHBoxLayout()
        run_btn = QPushButton("Add selected executable to startup")
        run_btn.clicked.connect(self._on_add_exec)
        run_row.addWidget(run_btn)
        layout.addLayout(run_row)

        return w

    def _on_add_startup(self):
        text, ok = self._prompt_text("Add startup command", "Command to run at shell startup (e.g. fastfetch or /usr/bin/someapp --flag):")
        if ok and text.strip():
            # append to end of file
            self.startup_cmds.append((None, text.strip()))
            item = QListWidgetItem(text.strip())
            item.setData(Qt.ItemDataRole.UserRole, None)
            self.startup_list.addItem(item)

    def _on_add_exec(self):
        txt = self.exec_combo.currentText().strip()
        if not txt:
            return
        self.startup_cmds.append((None, txt))
        item = QListWidgetItem(txt)
        item.setData(Qt.ItemDataRole.UserRole, None)
        self.startup_list.addItem(item)

    def _on_remove_startup(self):
        it = self.startup_list.currentItem()
        if not it:
            return
        row = self.startup_list.row(it)
        # mark removed by removing from list
        self.startup_list.takeItem(row)
        del self.startup_cmds[row]

    def _on_edit_startup(self):
        it = self.startup_list.currentItem()
        if not it:
            return
        row = self.startup_list.row(it)
        cur = it.text()
        text, ok = self._prompt_text("Edit startup command", "Command:", cur)
        if ok:
            it.setText(text)
            idx, _ = self.startup_cmds[row]
            self.startup_cmds[row] = (idx, text)

    # -----------------------------
    # Appearance tab
    # -----------------------------
    def _build_appearance_tab(self):
        w = QWidget()
        layout = QVBoxLayout()
        w.setLayout(layout)

        # PS1 editor (multiline safe via single-line input; keep simple)
        layout.addWidget(QLabel("PS1 prompt (raw string, escapes allowed):"))
        current_ps1 = self.entries.get("PS1", {}).get("val", "")
        # strip surrounding quotes if present
        if isinstance(current_ps1, str) and (current_ps1.startswith('"') or current_ps1.startswith("'")):
            current_ps1 = current_ps1[1:-1]
        self.ps1_input = QLineEdit(current_ps1)
        layout.addWidget(self.ps1_input)

        # color prompt toggle - try detect color_prompt variable presence
        color_prompt_val = self.entries.get("color_prompt", {}).get("val", "")
        cp_enabled = False
        try:
            cp_enabled = str(color_prompt_val).lower() in ("yes", "true", "1")
        except Exception:
            cp_enabled = False
        self.color_prompt_cb = QCheckBox("Enable color prompt (set color_prompt=yes)")
        self.color_prompt_cb.setChecked(cp_enabled)
        layout.addWidget(self.color_prompt_cb)

        # force_color_prompt toggle
        force_val = self.entries.get("force_color_prompt", {}).get("val", "")
        force_enabled = str(force_val).lower() in ("yes", "true", "1")
        self.force_cp_cb = QCheckBox("Force color prompt (set force_color_prompt=yes)")
        self.force_cp_cb.setChecked(force_enabled)
        layout.addWidget(self.force_cp_cb)

        return w

    # -----------------------------
    # Misc tab
    # -----------------------------
    def _build_misc_tab(self):
        w = QWidget()
        layout = QVBoxLayout()
        w.setLayout(layout)

        # HISTSIZE
        hist_val = self.entries.get("HISTSIZE", {}).get("val", "1000")
        try:
            hist_val_i = int(str(hist_val).strip())
        except Exception:
            hist_val_i = 1000
        layout.addWidget(QLabel("HISTSIZE"))
        self.hist_spin = QSpinBox()
        self.hist_spin.setRange(0, 10_000_000)
        self.hist_spin.setValue(hist_val_i)
        layout.addWidget(self.hist_spin)

        # HISTFILESIZE
        hfs = self.entries.get("HISTFILESIZE", {}).get("val", "2000")
        try:
            hfs_i = int(str(hfs).strip())
        except Exception:
            hfs_i = 2000
        layout.addWidget(QLabel("HISTFILESIZE"))
        self.histfile_spin = QSpinBox()
        self.histfile_spin.setRange(0, 10_000_000)
        self.histfile_spin.setValue(hfs_i)
        layout.addWidget(self.histfile_spin)

        # shopt histappend
        histappend_present = any("shopt histappend" in (v.get("text","") if v.get("kind")=="shopt" else "") for v in self.entries.values())
        self.histappend_cb = QCheckBox("Enable shopt histappend")
        self.histappend_cb.setChecked(histappend_present)
        layout.addWidget(self.histappend_cb)

        # shopt checkwinsize
        checkwinsize_present = any("shopt checkwinsize" in (v.get("text","") if v.get("kind")=="shopt" else "") for v in self.entries.values())
        self.checkwinsize_cb = QCheckBox("Enable shopt checkwinsize")
        self.checkwinsize_cb.setChecked(checkwinsize_present)
        layout.addWidget(self.checkwinsize_cb)

        # alias ls
        alias_ls = self.entries.get("alias:ls")
        ls_enabled = alias_ls is not None
        self.ls_alias_cb = QCheckBox("Enable ls color alias (alias ls='ls --color=auto')")
        self.ls_alias_cb.setChecked(ls_enabled)
        layout.addWidget(self.ls_alias_cb)

        # Assistant bind preview (if present)
        # try to detect 'ASSISTANT_CMD' variable
        assistant_var = None
        if "ASSISTANT_CMD" in self.entries:
            assistant_var = self.entries["ASSISTANT_CMD"].get("val")
        elif any("ASSISTANT_CMD" in (line or "") for line in self.lines):
            # not parsed, but present in file
            assistant_var = "present"
        if assistant_var:
            layout.addWidget(QLabel("Assistant command detected in bashrc."))

        return w

    # -----------------------------
    # Helpers: simple prompt
    # -----------------------------
    def _prompt_text(self, title, label, default=""):
        from PyQt5.QtWidgets import QInputDialog
        try:
            # Try PyQt6 style if available
            from PyQt6.QtWidgets import QInputDialog as QInputDialog6  # no-op, just to check availability
        except Exception:
            pass
        txt, ok = QInputDialog.getText(self, title, label, text=default)
        return txt, ok

    # -----------------------------
    # Save / write logic
    # -----------------------------
    def _on_refresh(self):
        self._load_source()
        # rebuild UI: clear and rebuild
        self._clear_layout(self.layout())
        self._build_ui()

    def _clear_layout(self, layout):
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            else:
                sub = item.layout()
                if sub is not None:
                    self._clear_layout(sub)

    def _on_save(self):
        # backup
        try:
            self._backup()
        except Exception:
            pass

        # modify a copy of lines
        lines = list(self.lines)

        # 1) replace assignments from misc & appearance
        def replace_or_append_assignment(key, value, prefix=""):
            # look for existing entry
            ent = self.entries.get(key)
            line = f"{prefix}{key}={value}\n"
            if ent and ent.get("line_idx") is not None:
                lines[ent["line_idx"]] = line
            else:
                # append at end
                lines.append(line)

        # HISTSIZE / HISTFILESIZE
        replace_or_append_assignment("HISTSIZE", str(self.hist_spin.value()))
        replace_or_append_assignment("HISTFILESIZE", str(self.histfile_spin.value()))

        # PS1 (quote the PS1 string)
        ps1_text = self.ps1_input.text()
        # escape existing $ etc — we store raw string in single quotes if contains double-quotes
        if "'" in ps1_text and '"' not in ps1_text:
            ps1_val = f'"{ps1_text}"'
        else:
            ps1_val = f"'{ps1_text}'"
        replace_or_append_assignment("PS1", ps1_val)

        # color_prompt / force_color_prompt
        if self.color_prompt_cb.isChecked():
            replace_or_append_assignment("color_prompt", "yes")
        else:
            replace_or_append_assignment("color_prompt", "no")
        if self.force_cp_cb.isChecked():
            replace_or_append_assignment("force_color_prompt", "yes")
        else:
            # remove or set to no
            replace_or_append_assignment("force_color_prompt", "no")

        # shopt histappend
        # find existing entry
        def replace_shopt(opt, enable):
            # find entry key 'shopt:opt'
            ent = self.entries.get(f"shopt:{opt}")
            line_txt = f"shopt -s {opt}\n" if enable else f"shopt -u {opt}\n"
            if ent and ent.get("line_idx") is not None:
                lines[ent["line_idx"]] = line_txt
            else:
                lines.append(line_txt)

        replace_shopt("histappend", self.histappend_cb.isChecked())
        replace_shopt("checkwinsize", self.checkwinsize_cb.isChecked())

        # alias ls
        if self.ls_alias_cb.isChecked():
            # set alias if absent
            ent = self.entries.get("alias:ls")
            alias_line = "alias ls='ls --color=auto'\n"
            if ent and ent.get("line_idx") is not None:
                lines[ent["line_idx"]] = alias_line
            else:
                lines.append(alias_line)
        else:
            ent = self.entries.get("alias:ls")
            if ent and ent.get("line_idx") is not None:
                # comment it out to preserve history
                lines[ent["line_idx"]] = "#" + (lines[ent["line_idx"]] if not lines[ent["line_idx"]].startswith("#") else lines[ent["line_idx"]])
            # else nothing to remove

        # 2) handle startup commands: take current list content from list widget
        new_startups = []
        for i in range(self.startup_list.count()):
            it = self.startup_list.item(i)
            txt = it.text().strip()
            new_startups.append(txt)

        # Strategy: remove all original detected startup_cmds lines, then append new_startups near end
        removed_idxs = [idx for idx, _ in self.startup_cmds if idx is not None]
        # build lines without removed startup lines
        filtered = [ln for j, ln in enumerate(lines) if j not in removed_idxs]
        # append a divider and the startup commands
        if new_startups:
            filtered.append("\n# Startup commands managed by BashSupport plugin\n")
            for cmd in new_startups:
                filtered.append(cmd.rstrip() + "\n")
        # set final lines
        final_lines = filtered

        # write out: prefer core_config save if available
        if self.using_core and hasattr(self.core_config, "path"):
            try:
                with open(self.core_config.path, "w", encoding="utf-8") as f:
                    f.writelines(final_lines)
                # try to call core save/load if available
                if hasattr(self.core_config, "load"):
                    try:
                        self.core_config.load()
                    except Exception:
                        pass
                if hasattr(self.core_config, "save"):
                    try:
                        self.core_config.save(backup=True)
                    except Exception:
                        pass
                QMessageBox.information(self, "Saved", f"Saved via core config at {self.core_config.path}")
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save via core config: {e}")
        else:
            try:
                self.bashrc_path.write_text("".join(final_lines), encoding="utf-8")
                QMessageBox.information(self, "Saved", f"Saved {self.bashrc_path} (backup created).")
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to write ~/.bashrc: {e}")

        # reload in-memory state
        self._load_source()

    # -----------------------------
    # End of class
    # -----------------------------
