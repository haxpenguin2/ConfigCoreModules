# plugin.py — Vim / Neovim editor plugin (multi-tab: Basic / Mappings / Raw)
import os
import re
import shutil
from pathlib import Path
from datetime import datetime

# Candidate vim config paths (user-level)
VIM_CANDIDATES = [
    os.path.expanduser("~/.vimrc"),
    os.path.expanduser("~/.config/nvim/init.vim"),    # Neovim
    os.path.expanduser("~/.config/vim/vimrc"),
]

def find_vim_path():
    for p in VIM_CANDIDATES:
        if os.path.isfile(p):
            return p
    # default to ~/.vimrc
    return VIM_CANDIDATES[0]

class VimConfig:
    """
    Minimal vimrc editor model that:
      - preserves all lines (comments, spacing)
      - recognizes 'set' lines (flags and key=value)
      - recognizes common mapping lines (map, nmap, nnoremap, inoremap, etc.)
      - provides get/set for 'set' options and mapping list manipulation
      - save() writes file with timestamped backup
    """
    SET_LINE_RE = re.compile(r'^\s*set\s+(.+)$', re.IGNORECASE)
    # captures forms: set option, set nooption, set opt=value, set opt^=value (we ignore complex operators)
    SET_OPT_RE = re.compile(r'^(?P<name>[^\s=:+-]+)(?:=(?P<val>.*))?$')
    # mapping line detection: starts with optional whitespace, then mapping command
    MAP_CMD_RE = re.compile(r'^\s*(?P<cmd>(?:[nvoixsctab]?nore)?map|map)\b', re.IGNORECASE)

    def __init__(self, path=None):
        self.path = Path(path or find_vim_path())
        self.lines = []
        self.load()

    def load(self):
        if self.path.exists():
            raw = self.path.read_text(encoding="utf-8", errors="surrogateescape")
            self.lines = raw.splitlines(True)
        else:
            self.lines = ["\n"]
        # normalize newlines
        self.lines = [ln if ln.endswith("\n") else ln + "\n" for ln in self.lines]

    # --------- SET options handling ----------
    def _find_set_line_idx(self, opt_name: str):
        """
        Return index of first 'set' line that mentions opt_name (exact token match),
        or None if not found.
        """
        key = opt_name.lower()
        for i, ln in enumerate(self.lines):
            m = self.SET_LINE_RE.match(ln)
            if not m:
                continue
            body = m.group(1).strip()
            # split on whitespace to tokens like "tabstop=4", "number", "nojoin"
            tokens = re.split(r'\s+', body)
            for tok in tokens:
                # handle 'no' prefix (e.g., nonumber)
                if tok.lower() == key or tok.lower() == ("no" + key):
                    return i
                # handle key=value forms
                if tok.lower().startswith(key + "=") or tok.lower().startswith(key + ":="):
                    return i
                # short forms: nu for number? we won't match short aliases
        return None

    def get(self, opt_name: str, default=None):
        """
        Return option value:
          - for flags: "true" if set (e.g., 'set number'), "false" if 'set nonumber'
          - for key=value: the RHS string
          - None / default if not present
        """
        idx = self._find_set_line_idx(opt_name)
        if idx is None:
            return default
        ln = self.lines[idx]
        m = self.SET_LINE_RE.match(ln)
        if not m:
            return default
        body = m.group(1).strip()
        # find the token corresponding to opt_name
        for tok in re.split(r'\s+', body):
            if tok.lower() == opt_name.lower():
                return "true"
            if tok.lower() == ("no" + opt_name.lower()):
                return "false"
            if tok.lower().startswith(opt_name.lower() + "="):
                val = tok.split("=", 1)[1]
                return val
        return default

    def set_existing(self, opt_name: str, value) -> bool:
        """
        Replace the token for an existing 'set' option if present.
        Returns True if modified, False if option not found.
        """
        idx = self._find_set_line_idx(opt_name)
        if idx is None:
            return False
        ln = self.lines[idx]
        m = self.SET_LINE_RE.match(ln)
        if not m:
            return False
        body = m.group(1)
        tokens = re.split(r'(\s+)', body)  # keep whitespace separators
        # tokens will be like ['tabstop=4', ' ', 'expandtab', ...] or include spaces
        changed = False
        for i, t in enumerate(tokens):
            if t.strip() == "":
                continue
            tok = t.strip()
            low = tok.lower()
            if low == opt_name.lower() or low == ("no" + opt_name.lower()) or low.startswith(opt_name.lower() + "="):
                # replace this token according to requested value
                if isinstance(value, bool):
                    newtok = opt_name if value else ("no" + opt_name)
                else:
                    s = str(value)
                    # if contains spaces, quote it
                    if " " in s and not (s.startswith('"') and s.endswith('"')):
                        s = f'"{s}"'
                    newtok = f"{opt_name}={s}"
                # preserve the original surrounding whitespace via tokens structure
                tokens[i] = newtok
                changed = True
                break
        if changed:
            # reconstruct body preserving separators
            newbody = "".join(tokens)
            # replace the line but preserve trailing comments if any
            # split original line into before-comment and comment
            parts = re.split(r'(#|\".*?\"|\'.*?\')', ln, maxsplit=1)
            # simpler: if line contains '#', treat everything after first unquoted # as comment
            comment = ""
            if "#" in ln:
                # find first # that is not inside quotes
                in_single = False
                in_double = False
                idx_sharp = None
                for pos, ch in enumerate(ln):
                    if ch == "'" and not in_double:
                        in_single = not in_single
                    elif ch == '"' and not in_single:
                        in_double = not in_double
                    elif ch == "#" and not in_single and not in_double:
                        idx_sharp = pos
                        break
                if idx_sharp is not None:
                    comment = ln[idx_sharp:].rstrip("\n")
            newline = f"set {newbody}"
            if comment:
                newline += " " + comment
            if not newline.endswith("\n"):
                newline += "\n"
            self.lines[idx] = newline
            return True
        return False

    def append_set(self, opt_name: str, value):
        """
        Append a 'set' token to the end of the file (as a new line). value may be bool, str, int.
        """
        if isinstance(value, bool):
            tok = opt_name if value else ("no" + opt_name)
        else:
            s = str(value)
            if " " in s and not (s.startswith('"') and s.endswith('"')):
                s = f'"{s}"'
            tok = f"{opt_name}={s}"
        if len(self.lines) and self.lines[-1].strip() != "":
            self.lines.append("\n")
        self.lines.append(f"set {tok}\n")
        return True

    # ----- Mappings handling -----
    def list_mappings(self):
        """
        Return list of tuples (idx, line) for all mapping lines detected.
        """
        items = []
        for i, ln in enumerate(self.lines):
            if self.MAP_CMD_RE.match(ln):
                items.append((i, ln.rstrip("\n")))
        return items

    def set_mapping_line(self, idx: int, new_line: str):
        """
        Replace mapping line at index idx with new_line.
        """
        if not (0 <= idx < len(self.lines)):
            raise IndexError("index out of range")
        if not new_line.endswith("\n"):
            new_line = new_line + "\n"
        self.lines[idx] = new_line
        return True

    def append_mapping(self, line: str):
        if not line.endswith("\n"):
            line = line + "\n"
        if len(self.lines) and self.lines[-1].strip() != "":
            self.lines.append("\n")
        self.lines.append(line)
        return True

    def remove_line(self, idx: int):
        if not (0 <= idx < len(self.lines)):
            return False
        self.lines.pop(idx)
        return True

    # ---- Save with backup ----
    def save(self, backup: bool = True):
        if backup and self.path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = self.path.with_suffix(self.path.suffix + f".bak.{ts}")
            try:
                shutil.copy2(self.path, bak)
            except Exception:
                # ignore backup errors but continue
                pass
        # ensure parent exists
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8", errors="surrogateescape") as f:
                f.writelines(self.lines)
        except Exception:
            raise

# ---------------- Lazy UI factory ----------------
def create_editor(core_config=None):
    try:
        from PyQt6.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QCheckBox, QSpinBox, QLineEdit,
            QPushButton, QMessageBox, QTabWidget, QListWidget, QListWidgetItem,
            QHBoxLayout, QDialog, QFormLayout, QComboBox, QTextEdit, QInputDialog
        )
        from PyQt6.QtCore import Qt
    except Exception:
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QCheckBox, QSpinBox, QLineEdit,
            QPushButton, QMessageBox, QTabWidget, QListWidget, QListWidgetItem,
            QHBoxLayout, QDialog, QFormLayout, QComboBox, QTextEdit, QInputDialog
        )
        from PyQt5.QtCore import Qt

    class VimEditor(QWidget):
        def __init__(self, *_):
            super().__init__()
            self.cfg = VimConfig(find_vim_path())
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout()
            self.setLayout(layout)
            layout.addWidget(QLabel(f"Editing: {self.cfg.path}"))

            self.tabs = QTabWidget()
            layout.addWidget(self.tabs)

            # Basic tab
            self.basic_tab = QWidget()
            b_layout = QVBoxLayout()
            self.basic_tab.setLayout(b_layout)

            # Common boolean options
            self.num_cb = QCheckBox("number")
            self.rnum_cb = QCheckBox("relativenumber")
            self.expandtab_cb = QCheckBox("expandtab")
            self.autoindent_cb = QCheckBox("autoindent")
            self.syntax_cb = QCheckBox("syntax on (toggle via 'syntax')")
            self.clipboard_cb = QCheckBox("clipboard=unnamedplus")

            # numeric options
            self.tabstop_spin = QSpinBox(); self.tabstop_spin.setRange(1, 16)
            self.shiftwidth_spin = QSpinBox(); self.shiftwidth_spin.setRange(0, 16)

            # set current values
            try:
                val = self.cfg.get("number", "false")
                self.num_cb.setChecked(str(val).strip().lower() == "true")
                val = self.cfg.get("relativenumber", "false")
                self.rnum_cb.setChecked(str(val).strip().lower() == "true")
                val = self.cfg.get("expandtab", "false")
                self.expandtab_cb.setChecked(str(val).strip().lower() == "true")
                val = self.cfg.get("autoindent", "false")
                self.autoindent_cb.setChecked(str(val).strip().lower() == "true")
                # syntax is often 'syntax on' rather than set; check for 'syntax on' by scanning raw lines
                self.syntax_cb.setChecked(any(ln.strip().lower().startswith("syntax on") for ln in self.cfg.lines))
                val = self.cfg.get("clipboard", "")
                self.clipboard_cb.setChecked("unnamed" in (val or "").lower() or "unnamedplus" in (val or "").lower())

                ts = self.cfg.get("tabstop", None)
                if ts is not None:
                    try: self.tabstop_spin.setValue(int(ts))
                    except Exception: pass
                sw = self.cfg.get("shiftwidth", None)
                if sw is not None:
                    try: self.shiftwidth_spin.setValue(int(sw))
                    except Exception: pass
            except Exception:
                pass

            b_layout.addWidget(self.num_cb)
            b_layout.addWidget(self.rnum_cb)
            b_layout.addWidget(self.expandtab_cb)
            b_layout.addWidget(self.autoindent_cb)
            b_layout.addWidget(self.syntax_cb)
            b_layout.addWidget(self.clipboard_cb)

            row = QHBoxLayout()
            row.addWidget(QLabel("tabstop"))
            row.addWidget(self.tabstop_spin)
            row.addWidget(QLabel("shiftwidth"))
            row.addWidget(self.shiftwidth_spin)
            b_layout.addLayout(row)

            save_basic_btn = QPushButton("Save Basic")
            save_basic_btn.clicked.connect(self._save_basic)
            b_layout.addWidget(save_basic_btn)

            self.tabs.addTab(self.basic_tab, "Basic")

            # Mappings tab
            self.maps_tab = QWidget()
            m_layout = QVBoxLayout()
            self.maps_tab.setLayout(m_layout)
            m_layout.addWidget(QLabel("Mappings (detected mapping lines)"))
            self.maps_list = QListWidget()
            m_layout.addWidget(self.maps_list)

            maps_row = QHBoxLayout()
            add_btn = QPushButton("Add")
            add_btn.clicked.connect(self._add_map)
            edit_btn = QPushButton("Edit")
            edit_btn.clicked.connect(self._edit_map)
            rm_btn = QPushButton("Remove")
            rm_btn.clicked.connect(self._remove_map)
            refresh_btn = QPushButton("Refresh")
            refresh_btn.clicked.connect(self._refresh_maps)
            maps_row.addWidget(add_btn)
            maps_row.addWidget(edit_btn)
            maps_row.addWidget(rm_btn)
            maps_row.addWidget(refresh_btn)
            m_layout.addLayout(maps_row)

            self.tabs.addTab(self.maps_tab, "Mappings")
            self._refresh_maps()

            # Raw tab
            self.raw_tab = QWidget()
            r_layout = QVBoxLayout()
            self.raw_tab.setLayout(r_layout)
            self.raw_edit = QTextEdit()
            # load raw content
            self.raw_edit.setPlainText("".join(self.cfg.lines))
            r_layout.addWidget(self.raw_edit)
            raw_row = QHBoxLayout()
            save_raw_btn = QPushButton("Save Raw (overwrite with backup)")
            save_raw_btn.clicked.connect(self._save_raw)
            raw_row.addWidget(save_raw_btn)
            r_layout.addLayout(raw_row)
            self.tabs.addTab(self.raw_tab, "Raw")

        # ---------- Basic save ----------
        def _save_basic(self):
            missing = []
            # prepare desired values
            desired = {
                "number": self.num_cb.isChecked(),
                "relativenumber": self.rnum_cb.isChecked(),
                "expandtab": self.expandtab_cb.isChecked(),
                "autoindent": self.autoindent_cb.isChecked(),
                "tabstop": str(self.tabstop_spin.value()),
                "shiftwidth": str(self.shiftwidth_spin.value()),
                "clipboard": "unnamedplus" if self.clipboard_cb.isChecked() else None
            }
            # syntax is special: not a 'set' option but a standalone 'syntax on' line
            want_syntax_on = self.syntax_cb.isChecked()
            # Try to set existing options
            for k, v in desired.items():
                if v is None:
                    # user wants to unset clipboard - we will not actively remove lines; skip
                    continue
                if not self.cfg.set_existing(k, v):
                    missing.append(("set", k, v))
            # syntax handling: find 'syntax on' or 'syntax off'
            syntax_idx = None
            for i, ln in enumerate(self.cfg.lines):
                if ln.strip().lower().startswith("syntax"):
                    syntax_idx = i
                    break
            if syntax_idx is None and want_syntax_on:
                missing.append(("syntax", "syntax", "on"))
            else:
                # if present, toggle it in-place
                if syntax_idx is not None:
                    if want_syntax_on:
                        self.cfg.lines[syntax_idx] = "syntax on\n"
                    else:
                        self.cfg.lines[syntax_idx] = "syntax off\n"

            # No missing -> save
            if not missing:
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved {self.cfg.path}")
                    # refresh raw and mappings
                    self.cfg.load()
                    self.raw_edit.setPlainText("".join(self.cfg.lines))
                    self._refresh_maps()
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return

            # Ask user whether to append missing set tokens
            msg = "Some options were not found in your vimrc and would be appended. Missing items:\n"
            for t, k, v in missing:
                msg += f" - {k} = {v}\n"
            msg += "\nAppend them? (No = save only existing changes)"
            resp = QMessageBox.question(self, "Append missing options?", msg,
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if resp == QMessageBox.StandardButton.Cancel:
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved existing changes to {self.cfg.path}")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return
            if resp == QMessageBox.StandardButton.No:
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved existing changes to {self.cfg.path}")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return

            # Yes -> append
            for _, k, v in missing:
                self.cfg.append_set(k, v)
            try:
                self.cfg.save(backup=True)
                QMessageBox.information(self, "Saved (with appended items)", f"Saved {self.cfg.path}")
                self.cfg.load()
                self.raw_edit.setPlainText("".join(self.cfg.lines))
                self._refresh_maps()
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")

        # ---------- Mappings UI ----------
        def _refresh_maps(self):
            self.maps_list.clear()
            items = self.cfg.list_mappings()
            for idx, line in items:
                it = QListWidgetItem(f"{idx}: {line}")
                it.setData(Qt.ItemDataRole.UserRole, idx)
                self.maps_list.addItem(it)

        def _add_map(self):
            # ask for mapping command components
            cmd_types = ["nnoremap", "inoremap", "vnoremap", "nmap", "imap", "map"]
            cmd, ok = QInputDialog.getItem(self, "Map type", "Command type:", cmd_types, editable=False)
            if not ok:
                return
            lhs, ok = QInputDialog.getText(self, "LHS", "Left-hand side (key):")
            if not ok or not lhs:
                return
            rhs, ok = QInputDialog.getText(self, "RHS", "Right-hand side (command):")
            if not ok:
                return
            new_line = f"{cmd} {lhs} {rhs}"
            self.cfg.append_mapping(new_line)
            try:
                self.cfg.save(backup=True)
                QMessageBox.information(self, "Added", "Mapping added.")
                self.cfg.load()
                self.raw_edit.setPlainText("".join(self.cfg.lines))
                self._refresh_maps()
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")

        def _edit_map(self):
            it = self.maps_list.currentItem()
            if not it:
                QMessageBox.information(self, "Select", "Select a mapping to edit.")
                return
            idx = it.data(Qt.ItemDataRole.UserRole)
            orig = self.cfg.lines[idx].rstrip("\n")
            # simple edit dialog: ask new full line
            new_line, ok = QInputDialog.getText(self, "Edit mapping", "Edit the mapping line:", text=orig)
            if not ok:
                return
            try:
                self.cfg.set_mapping_line(idx, new_line)
                self.cfg.save(backup=True)
                QMessageBox.information(self, "Saved", "Mapping updated.")
                self.cfg.load()
                self.raw_edit.setPlainText("".join(self.cfg.lines))
                self._refresh_maps()
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")

        def _remove_map(self):
            it = self.maps_list.currentItem()
            if not it:
                QMessageBox.information(self, "Select", "Select a mapping to remove.")
                return
            idx = it.data(Qt.ItemDataRole.UserRole)
            confirm = QMessageBox.question(self, "Confirm remove", f"Remove mapping line {idx}?")
            if confirm != QMessageBox.StandardButton.Yes:
                return
            if not self.cfg.remove_line(idx):
                QMessageBox.critical(self, "Remove failed", "Failed to remove mapping.")
                return
            try:
                self.cfg.save(backup=True)
                QMessageBox.information(self, "Removed", "Mapping removed.")
                self.cfg.load()
                self.raw_edit.setPlainText("".join(self.cfg.lines))
                self._refresh_maps()
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")

        # ---------- Raw save ----------
        def _save_raw(self):
            # overwrite entire file with the raw text; prompt user
            txt = self.raw_edit.toPlainText()
            confirm = QMessageBox.question(self, "Overwrite file?",
                                           "This will overwrite your vimrc with the text in the editor (a backup will be created). Continue?")
            if confirm != QMessageBox.StandardButton.Yes:
                return
            try:
                # write to model then save (ensures consistent backup procedure)
                self.cfg.lines = [ln if ln.endswith("\n") else ln + "\n" for ln in txt.splitlines(True)]
                self.cfg.save(backup=True)
                QMessageBox.information(self, "Saved", f"Saved {self.cfg.path}")
                self.cfg.load()
                self.raw_edit.setPlainText("".join(self.cfg.lines))
                self._refresh_maps()
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")

    return VimEditor(core_config)
