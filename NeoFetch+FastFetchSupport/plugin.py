# plugin.py — Fastfetch (JSONC) + Neofetch editor plugin (JSONC-aware for fastfetch)
# - Parses fastfetch's JSONC config.jsonc, exposes Modules / Logo / Display editing, and Raw editing.
# - Falls back to SimpleKeyConfig for older key=value-style configs (neofetch).
# - Backups made automatically. Comments removed on save (JSON pretty-printed).

import os
import re
import json
import shutil
from pathlib import Path
from datetime import datetime

# --- Paths (prefer config.jsonc for fastfetch) ---
FASTFETCH_PATHS = [
    os.path.expanduser("~/.config/fastfetch/config.jsonc"),
    os.path.expanduser("~/.config/fastfetch/config"),
    os.path.expanduser("~/.fastfetch/config.jsonc"),
    os.path.expanduser("~/.fastfetch/config"),
    "/etc/fastfetch/config.jsonc",
    "/etc/fastfetch/config",
]
NEOFETCH_PATHS = [
    os.path.expanduser("~/.config/neofetch/config.conf"),
    os.path.expanduser("~/.config/neofetch/config"),
    os.path.expanduser("~/.neofetch/config.conf"),
    os.path.expanduser("~/.neofetch/config"),
    "/etc/neofetch/config.conf",
    "/etc/neofetch/config",
]

def first_existing(paths):
    for p in paths:
        if os.path.isfile(p):
            return p
    return paths[0]

# ----------------------------
# JSONC handling for fastfetch
# ----------------------------
def strip_jsonc_comments(text: str) -> str:
    """
    Remove /* ... */ and //... comments from JSONC text.
    Conservative: removes multi-line and single-line comments.
    """
    # remove block comments first
    text_no_block = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # remove // comments (but not inside strings) -> use regex ignoring quotes roughly
    def _remove_line_comments(s):
        out_lines = []
        for line in s.splitlines():
            # naive approach: skip '//' that are inside quotes by scanning
            i = 0
            in_s = False
            in_d = False
            while i < len(line):
                ch = line[i]
                if ch == "'" and not in_d:
                    in_s = not in_s
                elif ch == '"' and not in_s:
                    in_d = not in_d
                elif ch == '/' and i+1 < len(line) and line[i+1] == '/' and not in_s and not in_d:
                    # cut the line here
                    line = line[:i]
                    break
                i += 1
            out_lines.append(line)
        return "\n".join(out_lines)
    return _remove_line_comments(text_no_block)

class FastfetchJSONModel:
    """
    Load, edit, and save a fastfetch JSONC config.
    - load(): reads raw text and builds `data` dict via json.loads after stripping comments
    - get(path, default=None): dot-separated path (e.g. 'logo.source' or 'display.color.title')
    - set(path, value): sets nested key, creating dicts as needed
    - modules helpers: list_modules(), set_module(idx, value), append_module(value), remove_module(idx)
    - save(): writes pretty JSON (comments lost) and makes backup
    """
    def __init__(self, path):
        self.path = Path(path)
        self.raw_text = ""
        self.data = {}
        self.load()

    def load(self):
        if self.path.exists():
            self.raw_text = self.path.read_text(encoding="utf-8", errors="surrogateescape")
            try:
                clean = strip_jsonc_comments(self.raw_text)
                self.data = json.loads(clean)
            except Exception:
                # if parsing fails, keep empty dict but preserve raw_text
                self.data = {}
        else:
            self.raw_text = ""
            self.data = {}

    def _backup(self):
        if self.path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = self.path.with_suffix(self.path.suffix + f".bak.{ts}")
            try:
                shutil.copy2(self.path, bak)
            except Exception:
                pass

    def _resolve_path(self, path: str):
        """Return (parent_dict, last_key) for dot-path, creating intermediate dicts if needed"""
        keys = path.split(".")
        cur = self.data
        for k in keys[:-1]:
            if not isinstance(cur.get(k), dict):
                cur[k] = {}
            cur = cur[k]
        return cur, keys[-1]

    def get(self, path: str, default=None):
        cur = self.data
        for p in path.split("."):
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    def set(self, path: str, value):
        parent, last = self._resolve_path(path)
        parent[last] = value
        return True

    # --- Modules helpers (fastfetch uses a 'modules' array) ---
    def list_modules(self):
        m = self.data.get("modules", [])
        if not isinstance(m, list):
            return []
        return m

    def set_module(self, idx: int, value):
        m = self.data.get("modules", [])
        if 0 <= idx < len(m):
            m[idx] = value
            self.data["modules"] = m
            return True
        return False

    def append_module(self, value):
        m = self.data.get("modules")
        if not isinstance(m, list):
            self.data["modules"] = []
        self.data["modules"].append(value)
        return True

    def remove_module(self, idx: int):
        m = self.data.get("modules", [])
        if 0 <= idx < len(m):
            m.pop(idx)
            self.data["modules"] = m
            return True
        return False

    def save(self, backup: bool = True):
        if backup:
            self._backup()
        # write pretty JSON; users editing comments should use Raw tab if they want to keep manual comments
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8", errors="surrogateescape") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except Exception:
            raise

# ---------------------------
# (Existing) SimpleKeyConfig for neofetch (unchanged)
# ---------------------------
# small/trimmed SimpleKeyConfig from earlier plugin (key=value style)
class SimpleKeyConfig:
    KEY_RE = re.compile(r'^(\s*{key}\s*)(?:=\s*(?P<val>[^#\n]*?))?(\s*(?P<comment>[#;].*)?)$', re.IGNORECASE)
    INFO_RE = re.compile(r'^\s*info\s+(?P<label>"[^"]*"|\'[^\']*\'|\S+)\s+(?P<value>\S+)(?P<rest>.*)$', re.IGNORECASE)

    def __init__(self, path):
        self.path = Path(path)
        self.lines = []
        self.load()

    def load(self):
        if self.path.exists():
            raw = self.path.read_text(encoding="utf-8", errors="surrogateescape")
            self.lines = raw.splitlines(True)
        else:
            self.lines = ["\n"]
        self.lines = [ln if ln.endswith("\n") else ln + "\n" for ln in self.lines]

    def _find_key_idx(self, key):
        pat = re.compile(self.KEY_RE.pattern.format(key=re.escape(key)), re.IGNORECASE)
        for i, ln in enumerate(self.lines):
            if pat.match(ln):
                return i
        return None

    def get(self, key, default=None):
        idx = self._find_key_idx(key)
        if idx is None:
            return default
        ln = self.lines[idx]
        pat = re.compile(self.KEY_RE.pattern.format(key=re.escape(key)))
        m = pat.match(ln)
        if not m:
            return default
        val = m.groupdict().get("val")
        if val is None:
            return ""
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            return val[1:-1]
        return val

    def set_existing(self, key, value) -> bool:
        idx = self._find_key_idx(key)
        if idx is None:
            return False
        ln = self.lines[idx]
        pat = re.compile(self.KEY_RE.pattern.format(key=re.escape(key)))
        m = pat.match(ln)
        if not m:
            self.lines[idx] = f"{key} = {value}\n"
            return True
        left = m.group(1)
        comment = m.groupdict().get("comment") or ""
        if comment and not comment.endswith("\n"):
            comment = comment + "\n"
        val_text = value
        if " " in val_text and not (val_text.startswith("(") and val_text.endswith(")")) and not ((val_text.startswith('"') and val_text.endswith('"')) or (val_text.startswith("'") and val_text.endswith("'"))):
            val_text = f'"{val_text}"'
        self.lines[idx] = f"{left}= {val_text}{comment}"
        return True

    def append_key(self, key, value):
        if not self.lines or not self.lines[-1].endswith("\n"):
            self.lines.append("\n")
        if len(self.lines) >= 1 and self.lines[-1].strip() != "":
            self.lines.append("\n")
        val_text = value
        if " " in val_text and not (val_text.startswith("(") and val_text.endswith(")")) and not ((val_text.startswith('"') and val_text.endswith('"')) or (val_text.startswith("'") and val_text.endswith("'"))):
            val_text = f'"{val_text}"'
        self.lines.append(f"{key}={val_text}\n")
        return True

    # Info lines for neofetch style (unchanged)
    def list_info(self):
        items = []
        for i, ln in enumerate(self.lines):
            m = self.INFO_RE.match(ln)
            if m:
                label = m.group("label").strip()
                value = m.group("value").strip()
                rest = m.group("rest") or ""
                if (label.startswith('"') and label.endswith('"')) or (label.startswith("'") and label.endswith("'")):
                    label = label[1:-1]
                items.append((i, label, value, rest.rstrip("\n")))
        return items

    def append_info(self, label, value):
        if not label:
            label = ""
        lbl = label
        if " " in lbl:
            lbl = f'"{lbl}"'
        line = f"info {lbl} {value}\n"
        if len(self.lines) and self.lines[-1].strip() != "":
            self.lines.append("\n")
        self.lines.append(line)
        return True

    def set_info_line(self, idx, label, value, rest=""):
        if not (0 <= idx < len(self.lines)):
            return False
        lbl = label
        if " " in lbl:
            lbl = f'"{lbl}"'
        rest_fmt = f" {rest}" if rest else ""
        self.lines[idx] = f"info {lbl} {value}{rest_fmt}\n"
        return True

    def remove_line(self, idx):
        if not (0 <= idx < len(self.lines)):
            return False
        self.lines.pop(idx)
        return True

    def save(self, backup=True):
        if backup and self.path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = self.path.with_suffix(self.path.suffix + f".bak.{ts}")
            try:
                shutil.copy2(self.path, bak)
            except Exception:
                pass
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8", errors="surrogateescape") as f:
            f.writelines(self.lines)

# ---------------------------
# GUI (lazy-loaded, PyQt6 preferred)
# ---------------------------
def create_editor(core_config=None):
    try:
        from PyQt6.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QPushButton, QTabWidget, QLineEdit,
            QHBoxLayout, QMessageBox, QListWidget, QListWidgetItem, QTextEdit,
            QFormLayout, QInputDialog, QGroupBox
        )
        from PyQt6.QtCore import Qt
    except Exception:
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QPushButton, QTabWidget, QLineEdit,
            QHBoxLayout, QMessageBox, QListWidget, QListWidgetItem, QTextEdit,
            QFormLayout, QInputDialog, QGroupBox
        )
        from PyQt5.QtCore import Qt

    class FetchEditor(QWidget):
        def __init__(self, *_):
            super().__init__()
            self.fast_path = first_existing(FASTFETCH_PATHS)
            self.neo_path = first_existing(NEOFETCH_PATHS)
            self.fast_is_jsonc = str(self.fast_path).lower().endswith(".jsonc") or os.path.isfile(self.fast_path)
            # pick default mode
            if os.path.isfile(self.fast_path):
                self.mode = "fastfetch"
            elif os.path.isfile(self.neo_path):
                self.mode = "neofetch"
            else:
                self.mode = "fastfetch"
            # load model(s)
            self._load_models()
            self._build_ui()

        def _load_models(self):
            # fastfetch: use JSON model if file endswith .jsonc or exists as jsonc
            if str(self.fast_path).lower().endswith(".jsonc") or (os.path.isfile(self.fast_path) and str(self.fast_path).lower().endswith(".jsonc")):
                self.fast_model = FastfetchJSONModel(self.fast_path)
            else:
                self.fast_model = SimpleKeyConfig(self.fast_path)
            self.neo_model = SimpleKeyConfig(self.neo_path)

        def _build_ui(self):
            layout = QVBoxLayout()
            self.setLayout(layout)
            hdr = QHBoxLayout()
            hdr.addWidget(QLabel("Mode:"))
            self.mode_box = QLineEdit(self.mode)  # simple indicator — core supplies mode select in larger UI
            self.mode_box.setReadOnly(True)
            hdr.addWidget(self.mode_box)
            hdr.addStretch()
            save_btn = QPushButton("Save (safe)")
            save_btn.clicked.connect(self._on_save)
            hdr.addWidget(save_btn)
            layout.addLayout(hdr)

            self.tabs = QTabWidget()
            layout.addWidget(self.tabs)

            # Modules tab (works for fastfetch JSON modules OR for neofetch's info lines)
            self.mods_tab = QWidget()
            mod_layout = QVBoxLayout()
            self.mods_tab.setLayout(mod_layout)
            mod_layout.addWidget(QLabel("Modules / Info items (order matters)"))
            self.mods_list = QListWidget()
            mod_layout.addWidget(self.mods_list)
            btn_row = QHBoxLayout()
            add_btn = QPushButton("Add")
            edit_btn = QPushButton("Edit")
            rm_btn = QPushButton("Remove")
            refresh_btn = QPushButton("Refresh")
            add_btn.clicked.connect(self._add_item)
            edit_btn.clicked.connect(self._edit_item)
            rm_btn.clicked.connect(self._remove_item)
            refresh_btn.clicked.connect(self._refresh_items)
            btn_row.addWidget(add_btn); btn_row.addWidget(edit_btn); btn_row.addWidget(rm_btn); btn_row.addWidget(refresh_btn)
            mod_layout.addLayout(btn_row)
            self.tabs.addTab(self.mods_tab, "Modules / Info")

            # Logo tab (fastfetch JSON)
            self.logo_tab = QWidget()
            logo_f = QFormLayout()
            self.logo_tab.setLayout(logo_f)
            self.logo_type = QLineEdit()
            self.logo_source = QLineEdit()
            logo_f.addRow(QLabel("logo.type"), self.logo_type)
            logo_f.addRow(QLabel("logo.source"), self.logo_source)
            self.tabs.addTab(self.logo_tab, "Logo")

            # Display tab (basic color title)
            self.display_tab = QWidget()
            display_f = QFormLayout()
            self.display_tab.setLayout(display_f)
            self.display_color_title = QLineEdit()
            display_f.addRow(QLabel("display.color.title"), self.display_color_title)
            self.tabs.addTab(self.display_tab, "Display")

            # Raw tab
            self.raw_tab = QWidget()
            rlay = QVBoxLayout()
            self.raw_tab.setLayout(rlay)
            rlay.addWidget(QLabel("Raw configuration (advanced). Overwrites file on save. Backup will be created."))
            self.raw_edit = QTextEdit()
            rlay.addWidget(self.raw_edit)
            self.tabs.addTab(self.raw_tab, "Raw")

            # Populate UI
            self._populate_ui()

        def _populate_ui(self):
            # Choose appropriate model based on mode; although mode UI here is minimal,
            # core will normally show plugin tab inside plugin list and you can choose config file externally.
            model = self.fast_model if self.mode == "fastfetch" else self.neo_model

            # Modules / Info items
            self._refresh_items()

            # Logo fields (for JSON-only)
            if isinstance(model, FastfetchJSONModel):
                logo = model.get("logo", {})
                if isinstance(logo, dict):
                    self.logo_type.setText(str(logo.get("type", "")))
                    self.logo_source.setText(str(logo.get("source", "")))
                else:
                    self.logo_type.setText("")
                    self.logo_source.setText("")
                # display color title
                dcol = model.get("display", {}).get("color", {}).get("title", "")
                self.display_color_title.setText(str(dcol))
                # raw text: show the original raw_text if available, else pretty JSON
                if getattr(model, "raw_text", ""):
                    self.raw_edit.setPlainText(model.raw_text)
                else:
                    self.raw_edit.setPlainText(json.dumps(model.data, indent=2))
            else:
                # key=value model: populate some GUI fields (best-effort)
                self.logo_type.setText("")
                self.logo_source.setText("")
                self.display_color_title.setText("")
                # raw
                if hasattr(model, "lines"):
                    self.raw_edit.setPlainText("".join(model.lines))
                else:
                    self.raw_edit.setPlainText("")

        # ------- Modules / Info helpers -------
        def _refresh_items(self):
            self.mods_list.clear()
            model = self.fast_model if self.mode == "fastfetch" else self.neo_model
            if isinstance(model, FastfetchJSONModel):
                items = model.list_modules()
                for i, item in enumerate(items):
                    # display as JSON string if object, or plain string
                    if isinstance(item, dict):
                        preview = json.dumps(item, separators=(", ", ": "))
                    else:
                        preview = str(item)
                    it = QListWidgetItem(f"{i}: {preview}")
                    it.setData(Qt.ItemDataRole.UserRole, i)
                    self.mods_list.addItem(it)
            else:
                # neofetch: use info lines
                items = model.list_info()
                for idx, label, value, rest in items:
                    display = f"{label}  →  {value}{(' '+rest) if rest else ''}"
                    it = QListWidgetItem(display)
                    it.setData(Qt.ItemDataRole.UserRole, idx)
                    self.mods_list.addItem(it)

        def _add_item(self):
            model = self.fast_model if self.mode == "fastfetch" else self.neo_model
            if isinstance(model, FastfetchJSONModel):
                # Add either a simple module string or a JSON object (ask raw JSON string)
                txt, ok = QInputDialog.getText(self, "Add module", "Enter module name (string) or JSON object (e.g. {\"type\":\"cpu\",\"temp\":true}):")
                if not ok or not txt.strip():
                    return
                s = txt.strip()
                try:
                    if s.startswith("{"):
                        val = json.loads(s)
                    else:
                        val = s
                    model.append_module(val)
                    QMessageBox.information(self, "Added", "Module appended.")
                    model.save(backup=False)
                    model.load()
                    self._populate_ui()
                except Exception as e:
                    QMessageBox.critical(self, "Invalid", f"Could not parse module: {e}")
            else:
                # neofetch info line: ask label and token
                label, ok = QInputDialog.getText(self, "Info Label", "Label (visible):")
                if not ok: return
                token, ok = QInputDialog.getText(self, "Info Token", "Token (e.g. distro, kernel, uptime):")
                if not ok: return
                model.append_info(label.strip(), token.strip())
                QMessageBox.information(self, "Added", "Info appended.")
                model.save(backup=False)
                model.load()
                self._populate_ui()

        def _edit_item(self):
            it = self.mods_list.currentItem()
            if not it:
                QMessageBox.information(self, "Select", "Select an item to edit.")
                return
            idx = it.data(Qt.ItemDataRole.UserRole)
            model = self.fast_model if self.mode == "fastfetch" else self.neo_model
            if isinstance(model, FastfetchJSONModel):
                cur = model.list_modules()[idx]
                if isinstance(cur, dict):
                    txt = json.dumps(cur, indent=2)
                else:
                    txt = str(cur)
                new_txt, ok = QInputDialog.getMultiLineText(self, "Edit module", "Edit module (string or JSON):", txt)
                if not ok: return
                new_s = new_txt.strip()
                try:
                    if new_s.startswith("{"):
                        val = json.loads(new_s)
                    else:
                        val = new_s
                    model.set_module(idx, val)
                    model.save(backup=False)
                    model.load()
                    QMessageBox.information(self, "Saved", "Module updated.")
                    self._populate_ui()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Could not set module: {e}")
            else:
                # neofetch mapping (line-based)
                items = model.list_info()
                for (i, label, value, rest) in items:
                    if i == idx:
                        orig = (i, label, value, rest)
                        break
                else:
                    QMessageBox.critical(self, "Error", "Could not find info line.")
                    return
                new_label, ok = QInputDialog.getText(self, "Edit label", "Label:", text=orig[1])
                if not ok: return
                new_value, ok = QInputDialog.getText(self, "Edit token", "Token:", text=orig[2])
                if not ok: return
                model.set_info_line(idx, new_label.strip(), new_value.strip(), orig[3])
                model.save(backup=False)
                model.load()
                QMessageBox.information(self, "Saved", "Info updated.")
                self._populate_ui()

        def _remove_item(self):
            it = self.mods_list.currentItem()
            if not it:
                QMessageBox.information(self, "Select", "Select an item to remove.")
                return
            idx = it.data(Qt.ItemDataRole.UserRole)
            model = self.fast_model if self.mode == "fastfetch" else self.neo_model
            confirm = QMessageBox.question(self, "Confirm remove", "Remove selected item?")
            if confirm != QMessageBox.StandardButton.Yes:
                return
            if isinstance(model, FastfetchJSONModel):
                ok = model.remove_module(idx)
            else:
                ok = model.remove_line(idx)
            if not ok:
                QMessageBox.critical(self, "Remove failed", "Failed to remove item.")
                return
            model.save(backup=False)
            model.load()
            self._populate_ui()

        # ------- Save button (writes GUI fields back to model) -------
        def _on_save(self):
            model = self.fast_model if self.mode == "fastfetch" else self.neo_model
            # if JSON model, set logo and display color fields
            if isinstance(model, FastfetchJSONModel):
                # logo
                ltype = self.logo_type.text().strip()
                lsrc = self.logo_source.text().strip()
                if ltype or lsrc:
                    logo = model.get("logo", {}) or {}
                    if ltype:
                        logo["type"] = ltype
                    if lsrc:
                        logo["source"] = lsrc
                    model.set("logo", logo)
                # display color title
                title_col = self.display_color_title.text().strip()
                if title_col:
                    # ensure nested dicts exist
                    disp = model.get("display", {}) or {}
                    color = disp.get("color", {}) or {}
                    color["title"] = title_col
                    disp["color"] = color
                    model.set("display", disp)
                # raw tab check: if raw edited, prefer raw save (ask)
                raw_txt = self.raw_edit.toPlainText().strip()
                if raw_txt:
                    # if raw differs from model.raw_text, ask user if they want to overwrite full file
                    if raw_txt != (model.raw_text or ""):
                        resp = QMessageBox.question(self, "Raw changed", "Raw text differs from parsed JSON. Overwrite full file with Raw tab content? (Yes = overwrite, No = write structured changes)", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
                        if resp == QMessageBox.StandardButton.Cancel:
                            return
                        if resp == QMessageBox.StandardButton.Yes:
                            # write raw text directly (create backup)
                            try:
                                model._backup()
                                model.path.write_text(raw_txt + ("\n" if not raw_txt.endswith("\n") else ""), encoding="utf-8", errors="surrogateescape")
                                QMessageBox.information(self, "Saved", f"Saved {model.path} (raw).")
                                model.load()
                                self._populate_ui()
                                return
                            except PermissionError:
                                QMessageBox.critical(self, "Permission denied", "Failed to save raw file (permission denied).")
                                return
                            except Exception as e:
                                QMessageBox.critical(self, "Save failed", f"Failed to write raw file: {e}")
                                return
                # otherwise persist structured changes
                try:
                    model.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved {model.path}")
                    model.load()
                    self._populate_ui()
                except PermissionError:
                    QMessageBox.critical(self, "Permission denied", "Failed to save: permission denied (system file?).")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
            else:
                # SimpleKeyConfig model: follow previous append/replace logic as before
                missing = []
                # try to set some common options (best-effort)
                # title
                t = self.logo_source.text().strip()
                if t:
                    if not model.set_existing("title", t):
                        missing.append(("title", t))
                # Attempt to write display.title color if possible
                if not model.set_existing("color_title", self.display_color_title.text().strip()):
                    # ignore if not present
                    pass
                # If any missing, ask about appending
                if missing:
                    msg = "Some keys not found and would be appended:\n"
                    for k, v in missing: msg += f" - {k} = {v}\n"
                    msg += "\nAppend them?"
                    resp = QMessageBox.question(self, "Append missing keys", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
                    if resp == QMessageBox.StandardButton.Cancel:
                        try:
                            model.save(backup=True)
                            QMessageBox.information(self, "Saved", f"Saved existing changes to {model.path}")
                        except Exception as e:
                            QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                        return
                    if resp == QMessageBox.StandardButton.No:
                        try:
                            model.save(backup=True)
                            QMessageBox.information(self, "Saved", f"Saved existing changes to {model.path}")
                        except Exception as e:
                            QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                        return
                    for k, v in missing:
                        model.append_key(k, v)
                try:
                    model.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved {model.path}")
                    model.load()
                    self._populate_ui()
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")

    return FetchEditor(core_config)
