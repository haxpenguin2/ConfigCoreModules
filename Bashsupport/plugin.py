# plugin.py
# BashSupport plugin — Startup Apps / Appearance / Misc / Keybindings
# Uses core_config only if it clearly refers to a bash-like file (fix requested).

import os, shutil, re
from pathlib import Path

# Try PyQt6 then PyQt5
try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
        QPushButton, QCheckBox, QSpinBox, QTabWidget, QListWidget, QListWidgetItem,
        QMessageBox, QInputDialog
    )
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLineEdit as QtLineEdit
except Exception:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
        QPushButton, QCheckBox, QSpinBox, QTabWidget, QListWidget, QListWidgetItem,
        QMessageBox, QInputDialog
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QLineEdit as QtLineEdit

# Regex helpers
ASSIGN_RE = re.compile(r'^(?P<prefix>export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<val>.+)$')
SHOPT_RE = re.compile(r'^\s*shopt\s+(-s|-u)?\s*(?P<opt>\w+)\s*$')
ALIAS_RE = re.compile(r'^\s*alias\s+(?P<key>[\w\-]+)=(?P<val>.+)$')
FUNCTION_START_RE = re.compile(r'^\s*(?:(?:function\s+\w+)|(?:\w+\s*\(\s*\)))\s*\{')
FUNCTION_END_RE = re.compile(r'^\s*\}')
SETOPT_RE = re.compile(r'^\s*set\s+-o\s+(?P<opt>\w+)\s+(?P<val>\w+)\s*$')
BINDX_RE = re.compile(r'^\s*bind\s+-x\s+(?P<expr>.+)$')

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
    EditorWidget(core_config=None)

    core_config: optional object from core. Use it only if its path obviously refers to a bashrc/shell file.
    Otherwise prefer ~/.bashrc.
    """
    def __init__(self, core_config=None):
        super().__init__()

        self.core_config = core_config

        # choose file to edit: prefer ~/.bashrc unless core_config points to a shell file
        default_bashrc = Path.home() / ".bashrc"
        self.bashrc_path = default_bashrc
        self.using_core = False

        try:
            core_path = None
            if self.core_config is not None and hasattr(self.core_config, "path"):
                core_path = Path(getattr(self.core_config, "path"))
            if core_path:
                name = core_path.name.lower()
                full = str(core_path).lower()
                if ("bashrc" in name) or (name.endswith(".sh")) or ("bash" in full and "i3" not in full):
                    self.bashrc_path = core_path
                    self.using_core = True
                else:
                    self.bashrc_path = default_bashrc
                    self.using_core = False
        except Exception:
            self.bashrc_path = default_bashrc
            self.using_core = False

        # internal state
        self.lines = []          # list of lines with newline endings
        self.entries = {}        # parsed assignments / shopt / alias entries
        self.startup_cmds = []   # list of (line_idx or None, text)
        self.keybinds = []       # list of (line_idx or None, expr_text)

        # header label so user sees which file is being edited
        self.header_label = QLabel()
        self._load_source()
        self._build_ui()

    # -----------------------------
    # Loading & parsing
    # -----------------------------
    def _load_source(self):
        # if using_core and core_config has .lines, prefer that (but normalize newlines)
        if self.using_core and self.core_config is not None and hasattr(self.core_config, "lines"):
            try:
                raw_lines = list(self.core_config.lines)
                # core's lines often don't have trailing newlines (splitlines). normalize.
                self.lines = [ln if ln.endswith("\n") else ln + "\n" for ln in raw_lines]
            except Exception:
                self.using_core = False

        if not self.using_core:
            if self.bashrc_path.exists():
                self.lines = self.bashrc_path.read_text(encoding="utf-8").splitlines(True)
            else:
                self.lines = []

        # parse file into entries/startup/keybind lists
        self._parse_lines()

    def _parse_lines(self):
        self.entries = {}
        self.startup_cmds = []
        self.keybinds = []
        in_function = False

        for idx, raw in enumerate(self.lines):
            s = raw.strip()
            if FUNCTION_START_RE.match(s):
                in_function = True
            if in_function:
                if FUNCTION_END_RE.match(s):
                    in_function = False
                continue
            if not s or s.startswith("#"):
                continue

            mb = BINDX_RE.match(s)
            if mb:
                expr = mb.group("expr").strip()
                self.keybinds.append((idx, expr))
                continue

            m = ASSIGN_RE.match(s)
            if m:
                key = m.group("key")
                val = m.group("val").strip()
                prefix = m.group("prefix") or ""
                self.entries[key] = {"line_idx": idx, "kind": "assign", "prefix": prefix, "val": val}
                continue

            m2 = SHOPT_RE.match(s)
            if m2:
                opt = m2.group("opt")
                self.entries[f"shopt:{opt}"] = {"line_idx": idx, "kind": "shopt", "text": s}
                continue

            m3 = SETOPT_RE.match(s)
            if m3:
                opt = m3.group("opt")
                val = m3.group("val")
                self.entries[f"setopt:{opt}"] = {"line_idx": idx, "kind": "setopt", "val": val}
                continue

            ma = ALIAS_RE.match(s)
            if ma:
                key = ma.group("key")
                val = ma.group("val")
                self.entries[f"alias:{key}"] = {"line_idx": idx, "kind": "alias", "val": val}
                continue

            # fallback: simple startup command candidate
            if ("=" not in s) and (s.find(";") == -1) and (not s.startswith("if ")) and (not s.startswith("case ")) and (not s.startswith("for ")) and (not s.startswith("while ")) and (not s.startswith("function ")):
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

        # header
        self.header_label.setText(f"Editing: {self.bashrc_path}")
        root.addWidget(self.header_label)

        tabs = QTabWidget()
        root.addWidget(tabs)

        tabs.addTab(self._build_startup_tab(), "Startup apps")
        tabs.addTab(self._build_appearance_tab(), "Appearance")
        tabs.addTab(self._build_misc_tab(), "Misc")
        tabs.addTab(self._build_keybindings_tab(), "Keybindings")

        # Save / Refresh row
        row = QHBoxLayout()
        save_btn = QPushButton("Save changes")
        save_btn.clicked.connect(self._on_save)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._on_refresh)
        row.addWidget(save_btn)
        row.addWidget(refresh_btn)
        root.addLayout(row)

    # ---------- Startup tab ----------
    def _build_startup_tab(self):
        w = QWidget(); layout = QVBoxLayout(); w.setLayout(layout)
        layout.addWidget(QLabel("Detected startup commands (simple, not inside functions):"))
        self.startup_list = QListWidget()
        for idx, txt in self.startup_cmds:
            item = QListWidgetItem(txt)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.startup_list.addItem(item)
        layout.addWidget(self.startup_list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add command"); add_btn.clicked.connect(self._on_add_startup)
        edit_btn = QPushButton("Edit selected"); edit_btn.clicked.connect(self._on_edit_startup)
        rm_btn = QPushButton("Remove selected"); rm_btn.clicked.connect(self._on_remove_startup)
        btn_row.addWidget(add_btn); btn_row.addWidget(edit_btn); btn_row.addWidget(rm_btn)
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("Quick pick installed executable (searchable):"))
        self.exec_combo = QComboBox(); self.exec_combo.setEditable(True)
        for exe in list_path_executables():
            self.exec_combo.addItem(exe)
        layout.addWidget(self.exec_combo)
        run_row = QHBoxLayout()
        run_btn = QPushButton("Add selected executable to startup"); run_btn.clicked.connect(self._on_add_exec)
        run_row.addWidget(run_btn)
        layout.addLayout(run_row)
        return w

    def _on_add_startup(self):
        txt, ok = self._prompt_text("Add startup command", "Command to run at shell startup:")
        if ok and txt.strip():
            self.startup_cmds.append((None, txt.strip()))
            item = QListWidgetItem(txt.strip()); item.setData(Qt.ItemDataRole.UserRole, None)
            self.startup_list.addItem(item)

    def _on_add_exec(self):
        txt = self.exec_combo.currentText().strip()
        if txt:
            self.startup_cmds.append((None, txt))
            item = QListWidgetItem(txt); item.setData(Qt.ItemDataRole.UserRole, None)
            self.startup_list.addItem(item)

    def _on_remove_startup(self):
        it = self.startup_list.currentItem()
        if not it: return
        row = self.startup_list.row(it)
        self.startup_list.takeItem(row)
        del self.startup_cmds[row]

    def _on_edit_startup(self):
        it = self.startup_list.currentItem()
        if not it: return
        row = self.startup_list.row(it)
        cur = it.text()
        txt, ok = self._prompt_text("Edit startup command", "Command:", cur)
        if ok:
            it.setText(txt)
            idx, _ = self.startup_cmds[row]
            self.startup_cmds[row] = (idx, txt)

    # ---------- Appearance ----------
    def _build_appearance_tab(self):
        w = QWidget(); layout = QVBoxLayout(); w.setLayout(layout)
        current_ps1 = self.entries.get("PS1", {}).get("val", "")
        if isinstance(current_ps1, str) and (current_ps1.startswith('"') or current_ps1.startswith("'")):
            current_ps1 = current_ps1[1:-1]
        self.ps1_input = QLineEdit(current_ps1)
        layout.addWidget(QLabel("PS1 prompt (raw string, escapes allowed):"))
        layout.addWidget(self.ps1_input)

        cp_val = self.entries.get("color_prompt", {}).get("val", "no")
        cp_enabled = str(cp_val).lower() in ("yes", "true", "1")
        self.color_prompt_cb = QCheckBox("Enable color prompt (set color_prompt=yes)")
        self.color_prompt_cb.setChecked(cp_enabled)
        layout.addWidget(self.color_prompt_cb)

        force_val = self.entries.get("force_color_prompt", {}).get("val", "no")
        force_enabled = str(force_val).lower() in ("yes", "true", "1")
        self.force_cp_cb = QCheckBox("Force color prompt (set force_color_prompt=yes)")
        self.force_cp_cb.setChecked(force_enabled)
        layout.addWidget(self.force_cp_cb)

        return w

    # ---------- Misc ----------
    def _build_misc_tab(self):
        w = QWidget(); layout = QVBoxLayout(); w.setLayout(layout)
        hist_v = self.entries.get("HISTSIZE", {}).get("val", "1000")
        try: hist_i = int(str(hist_v).strip())
        except: hist_i = 1000
        layout.addWidget(QLabel("HISTSIZE"))
        self.hist_spin = QSpinBox(); self.hist_spin.setRange(0, 10_000_000); self.hist_spin.setValue(hist_i); layout.addWidget(self.hist_spin)

        hfs = self.entries.get("HISTFILESIZE", {}).get("val", "2000")
        try: hfs_i = int(str(hfs).strip())
        except: hfs_i = 2000
        layout.addWidget(QLabel("HISTFILESIZE"))
        self.histfile_spin = QSpinBox(); self.histfile_spin.setRange(0, 10_000_000); self.histfile_spin.setValue(hfs_i); layout.addWidget(self.histfile_spin)

        histappend_present = any(k.startswith("shopt:histappend") for k in self.entries.keys())
        self.histappend_cb = QCheckBox("Enable shopt histappend"); self.histappend_cb.setChecked(histappend_present); layout.addWidget(self.histappend_cb)

        checkwinsize_present = any(k.startswith("shopt:checkwinsize") for k in self.entries.keys())
        self.checkwinsize_cb = QCheckBox("Enable shopt checkwinsize"); self.checkwinsize_cb.setChecked(checkwinsize_present); layout.addWidget(self.checkwinsize_cb)

        alias_ls = self.entries.get("alias:ls")
        self.ls_alias_cb = QCheckBox("Enable ls color alias (alias ls='ls --color=auto')")
        self.ls_alias_cb.setChecked(alias_ls is not None)
        layout.addWidget(self.ls_alias_cb)

        return w

    # ---------- Keybindings ----------
    def _build_keybindings_tab(self):
        w = QWidget(); layout = QVBoxLayout(); w.setLayout(layout)
        layout.addWidget(QLabel("bind -x keybindings detected:"))
        self.bind_list = QListWidget()
        for idx, expr in self.keybinds:
            it = QListWidgetItem(expr)
            it.setData(Qt.ItemDataRole.UserRole, idx)
            self.bind_list.addItem(it)
        layout.addWidget(self.bind_list)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add binding"); add_btn.clicked.connect(self._on_add_bind)
        edit_btn = QPushButton("Edit selected"); edit_btn.clicked.connect(self._on_edit_bind)
        rm_btn = QPushButton("Remove selected"); rm_btn.clicked.connect(self._on_remove_bind)
        btn_row.addWidget(add_btn); btn_row.addWidget(edit_btn); btn_row.addWidget(rm_btn)
        layout.addLayout(btn_row)
        layout.addWidget(QLabel('Example entry: "\\C-@":toggle_assistant  (include quotes if using special chars)'))
        return w

    def _on_add_bind(self):
        txt, ok = self._prompt_text("Add keybinding", 'Enter bind -x expression (e.g. "\\C-@":toggle_assistant):')
        if ok and txt.strip():
            self.keybinds.append((None, txt.strip()))
            it = QListWidgetItem(txt.strip()); it.setData(Qt.ItemDataRole.UserRole, None); self.bind_list.addItem(it)

    def _on_edit_bind(self):
        it = self.bind_list.currentItem()
        if not it: return
        row = self.bind_list.row(it)
        cur = it.text()
        txt, ok = self._prompt_text("Edit binding", "Binding expression:", cur)
        if ok:
            it.setText(txt); idx, _ = self.keybinds[row]; self.keybinds[row] = (idx, txt)

    def _on_remove_bind(self):
        it = self.bind_list.currentItem()
        if not it: return
        row = self.bind_list.row(it); self.bind_list.takeItem(row); del self.keybinds[row]

    # ---------- dialog helper ----------
    def _prompt_text(self, title, label, default=""):
        """
        Use QInputDialog.getText in a signature-compatible way across PyQt5/6.
        """
        try:
            txt, ok = QInputDialog.getText(self, title, label, QtLineEdit.EchoMode.Normal, default)
        except TypeError:
            try:
                txt, ok = QInputDialog.getText(self, title, label, QtLineEdit.Normal, default)
            except Exception:
                txt, ok = QInputDialog.getText(self, title, label)
        return txt, ok

    # ---------- refresh / clear ----------
    def _on_refresh(self):
        self._load_source()
        self._clear_layout(self.layout())
        self._build_ui()

    def _clear_layout(self, layout):
        if layout is None: return
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            else:
                sub = item.layout()
                if sub is not None:
                    self._clear_layout(sub)

    # ---------- save ----------
    def _on_save(self):
        try:
            self._backup()
        except Exception:
            pass

        lines = list(self.lines)

        def replace_or_append_assign(key, value, prefix=""):
            ent = self.entries.get(key)
            line = f"{prefix}{key}={value}\n"
            if ent and ent.get("line_idx") is not None:
                lines[ent["line_idx"]] = line
            else:
                lines.append(line)

        # HISTSIZE / HISTFILESIZE
        replace_or_append_assign("HISTSIZE", str(self.hist_spin.value()))
        replace_or_append_assign("HISTFILESIZE", str(self.histfile_spin.value()))

        # PS1
        ps1_text = self.ps1_input.text()
        ps1_val = f"'{ps1_text}'" if '"' not in ps1_text else f'"{ps1_text}"'
        replace_or_append_assign("PS1", ps1_val)

        # color prompt flags
        replace_or_append_assign("color_prompt", "yes" if self.color_prompt_cb.isChecked() else "no")
        replace_or_append_assign("force_color_prompt", "yes" if self.force_cp_cb.isChecked() else "no")

        # shopt options
        def replace_shopt(opt, enable):
            ent = self.entries.get(f"shopt:{opt}")
            line = f"shopt -s {opt}\n" if enable else f"shopt -u {opt}\n"
            if ent and ent.get("line_idx") is not None:
                lines[ent["line_idx"]] = line
            else:
                lines.append(line)
        replace_shopt("histappend", self.histappend_cb.isChecked())
        replace_shopt("checkwinsize", self.checkwinsize_cb.isChecked())

        # alias ls
        if self.ls_alias_cb.isChecked():
            ent = self.entries.get("alias:ls")
            alias_line = "alias ls='ls --color=auto'\n"
            if ent and ent.get("line_idx") is not None:
                lines[ent["line_idx"]] = alias_line
            else:
                lines.append(alias_line)
        else:
            ent = self.entries.get("alias:ls")
            if ent and ent.get("line_idx") is not None:
                idx = ent["line_idx"]
                if not lines[idx].lstrip().startswith("#"):
                    lines[idx] = "# " + lines[idx]

        # Startup commands: remove original detected lines, append new list
        removed_idxs = [i for i, _ in self.startup_cmds if i is not None]
        filtered = [ln for j, ln in enumerate(lines) if j not in removed_idxs]
        new_startups = [self.startup_list.item(i).text().rstrip() for i in range(self.startup_list.count())]
        if new_startups:
            filtered.append("\n# Startup commands managed by BashSupport plugin\n")
            for cmd in new_startups:
                filtered.append(cmd.rstrip() + "\n")
        final_lines = filtered

        # Keybindings: remove detected bind -x lines and append new ones
        removed_bind_idxs = [i for i, _ in self.keybinds if i is not None]
        filtered2 = [ln for j, ln in enumerate(final_lines) if j not in removed_bind_idxs]
        new_binds = [self.bind_list.item(i).text().rstrip() for i in range(self.bind_list.count())]
        if new_binds:
            filtered2.append("\n# Keybindings managed by BashSupport plugin\n")
            for b in new_binds:
                filtered2.append("bind -x " + b.rstrip() + "\n")
        final_lines = filtered2

        # Write via core_config if available and using_core, else write file
        if self.using_core and hasattr(self.core_config, "path"):
            try:
                with open(self.core_config.path, "w", encoding="utf-8") as f:
                    f.writelines(final_lines)
                # try to call core load/save hooks
                if hasattr(self.core_config, "load"):
                    try: self.core_config.load()
                    except: pass
                if hasattr(self.core_config, "save"):
                    try: self.core_config.save(backup=True)
                    except: pass
                QMessageBox.information(self, "Saved", f"Saved via core config at {self.core_config.path}")
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save via core config: {e}")
        else:
            try:
                self.bashrc_path.write_text("".join(final_lines), encoding="utf-8")
                QMessageBox.information(self, "Saved", f"Saved {self.bashrc_path} (backup created).")
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to write ~/.bashrc: {e}")

        # reload memory
        self._load_source()
