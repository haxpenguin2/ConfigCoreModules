# plugin.py — Fastfetch (JSONC) + Neofetch editor (drop-in)
# - Parses fastfetch's JSONC config.jsonc, edits ascii_path/ascii_colors/modules/logo/display, and saves (backup).
# - Falls back to a conservative line-based editor for neofetch.
# - Provides a GUI with tabs and a Browse button to pick an ASCII art file.

import os
import re
import json
import shutil
from pathlib import Path
from datetime import datetime

# Prefer user config.jsonc for fastfetch
FASTFETCH_PATHS = [
    os.path.expanduser("~/.config/fastfetch/config.jsonc"),
    os.path.expanduser("~/.config/fastfetch/config"),
    os.path.expanduser("~/.fastfetch/config.jsonc"),
    "/etc/fastfetch/config.jsonc",
    "/etc/fastfetch/config",
]
NEOFETCH_PATHS = [
    os.path.expanduser("~/.config/neofetch/config.conf"),
    os.path.expanduser("~/.neofetch/config.conf"),
    "/etc/neofetch/config.conf",
]

def first_existing(paths):
    for p in paths:
        if os.path.isfile(p):
            return p
    return paths[0]

# -----------------------
# JSONC utilities
# -----------------------
def strip_jsonc_comments(text: str) -> str:
    """
    Remove /* ... */ and // ... comments from JSONC text.
    This is conservative but practical for most fastfetch configs.
    """
    # remove block comments first
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # remove // comments that are not inside quotes (best-effort)
    out_lines = []
    for line in text.splitlines():
        i = 0
        in_s = False
        in_d = False
        cut_at = None
        while i < len(line) - 1:
            ch = line[i]
            nxt = line[i+1]
            if ch == "'" and not in_d:
                in_s = not in_s
            elif ch == '"' and not in_s:
                in_d = not in_d
            elif ch == '/' and nxt == '/' and not in_s and not in_d:
                cut_at = i
                break
            i += 1
        if cut_at is not None:
            out_lines.append(line[:cut_at])
        else:
            out_lines.append(line)
    return "\n".join(out_lines)

# -----------------------
# Fastfetch JSON model
# -----------------------
class FastfetchJSONModel:
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
                self.data = json.loads(clean) if clean.strip() else {}
            except Exception:
                # parse error -> keep empty dict but preserve raw_text
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

    def get(self, path, default=None):
        # dot-path like logo.source
        cur = self.data
        for p in path.split("."):
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    def set(self, path, value):
        cur = self.data
        parts = path.split(".")
        for p in parts[:-1]:
            if not isinstance(cur.get(p), dict):
                cur[p] = {}
            cur = cur[p]
        cur[parts[-1]] = value
        return True

    # modules helpers
    def list_modules(self):
        m = self.data.get("modules", [])
        return m if isinstance(m, list) else []

    def append_module(self, v):
        if "modules" not in self.data or not isinstance(self.data["modules"], list):
            self.data["modules"] = []
        self.data["modules"].append(v)
        return True

    def set_module(self, idx, v):
        if "modules" not in self.data or not isinstance(self.data["modules"], list):
            return False
        if 0 <= idx < len(self.data["modules"]):
            self.data["modules"][idx] = v
            return True
        return False

    def remove_module(self, idx):
        if "modules" not in self.data or not isinstance(self.data["modules"], list):
            return False
        if 0 <= idx < len(self.data["modules"]):
            self.data["modules"].pop(idx)
            return True
        return False

    def save(self, backup=True):
        if backup:
            self._backup()
        # write pretty JSON (comments will be lost)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8", errors="surrogateescape") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        # reload raw_text
        self.load()

# -----------------------
# Simple key=value config (neofetch style)
# -----------------------
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
        # quote if contains spaces
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

# -----------------------
# GUI (lazy)
# -----------------------
def create_editor(core_config=None):
    try:
        from PyQt6.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QPushButton, QTabWidget, QLineEdit,
            QHBoxLayout, QMessageBox, QListWidget, QListWidgetItem, QTextEdit,
            QFormLayout, QInputDialog, QFileDialog, QCheckBox, QGroupBox
        )
        from PyQt6.QtCore import Qt
    except Exception:
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QPushButton, QTabWidget, QLineEdit,
            QHBoxLayout, QMessageBox, QListWidget, QListWidgetItem, QTextEdit,
            QFormLayout, QInputDialog, QFileDialog, QCheckBox, QGroupBox
        )
        from PyQt5.QtCore import Qt

    class FetchEditor(QWidget):
        def __init__(self, *_):
            super().__init__()
            self.fast_path = first_existing(FASTFETCH_PATHS)
            self.neo_path = first_existing(NEOFETCH_PATHS)
            # choose which mode based on which file exists (user config preferred)
            if os.path.isfile(self.fast_path):
                self.mode = "fastfetch"
            elif os.path.isfile(self.neo_path):
                self.mode = "neofetch"
            else:
                self.mode = "fastfetch"
            # load models
            self._load_models()
            self._build_ui()

        def _load_models(self):
            if str(self.fast_path).lower().endswith(".jsonc") or os.path.isfile(self.fast_path) and str(self.fast_path).lower().endswith(".jsonc"):
                self.fast_model = FastfetchJSONModel(self.fast_path)
            else:
                # fallback: some fastfetch setups may not use jsonc; still try JSON model when possible
                try:
                    self.fast_model = FastfetchJSONModel(self.fast_path)
                except Exception:
                    self.fast_model = SimpleKeyConfig(self.fast_path)
            self.neo_model = SimpleKeyConfig(self.neo_path)

        def _build_ui(self):
            layout = QVBoxLayout()
            self.setLayout(layout)

            top = QHBoxLayout()
            top.addWidget(QLabel("Mode:"))
            self.mode_sel = QLineEdit(self.mode)
            self.mode_sel.setReadOnly(True)
            top.addWidget(self.mode_sel)
            top.addStretch()
            save_btn = QPushButton("Save (safe)")
            save_btn.clicked.connect(self._on_save)
            top.addWidget(save_btn)
            layout.addLayout(top)

            self.tabs = QTabWidget()
            layout.addWidget(self.tabs)

            # Modules / Info tab
            self.mods_tab = QWidget()
            ml = QVBoxLayout(); self.mods_tab.setLayout(ml)
            ml.addWidget(QLabel("Modules / Info items (order matters)"))
            self.mods_list = QListWidget()
            ml.addWidget(self.mods_list)
            btns = QHBoxLayout()
            add_btn = QPushButton("Add"); add_btn.clicked.connect(self._add_item)
            edit_btn = QPushButton("Edit"); edit_btn.clicked.connect(self._edit_item)
            rm_btn = QPushButton("Remove"); rm_btn.clicked.connect(self._remove_item)
            ref_btn = QPushButton("Refresh"); ref_btn.clicked.connect(self._refresh_items)
            btns.addWidget(add_btn); btns.addWidget(edit_btn); btns.addWidget(rm_btn); btns.addWidget(ref_btn)
            ml.addLayout(btns)
            self.tabs.addTab(self.mods_tab, "Modules / Info")

            # ASCII / Image tab
            self.ascii_tab = QWidget()
            af = QFormLayout(); self.ascii_tab.setLayout(af)
            self.backend_le = QLineEdit(); self.backend_le.setPlaceholderText("ascii / image / off")
            self.ascii_distro_le = QLineEdit(); self.ascii_distro_le.setPlaceholderText("Distro for ascii art (e.g. Arch)")
            # ascii path with browse
            row = QHBoxLayout()
            self.ascii_file_le = QLineEdit(); self.ascii_file_le.setPlaceholderText("/path/to/ascii.txt")
            browse = QPushButton("Browse…")
            browse.clicked.connect(self._browse_ascii_file)
            row.addWidget(self.ascii_file_le); row.addWidget(browse)
            self.ascii_bold_cb = QCheckBox("ASCII bold")
            af.addRow(QLabel("Mode"), self.backend_le)
            af.addRow(QLabel("ASCII distro"), self.ascii_distro_le)
            af.addRow(QLabel("ASCII file"), row)
            af.addRow(self.ascii_bold_cb)
            self.tabs.addTab(self.ascii_tab, "ASCII / Image")

            # Logo & Display tab (logo.type/logo.source, basic display colors)
            self.logo_tab = QWidget()
            lf = QFormLayout(); self.logo_tab.setLayout(lf)
            self.logo_type_le = QLineEdit(); self.logo_source_le = QLineEdit()
            self.display_title_color_le = QLineEdit()
            lf.addRow(QLabel("logo.type"), self.logo_type_le)
            lf.addRow(QLabel("logo.source"), self.logo_source_le)
            lf.addRow(QLabel("display.color.title"), self.display_title_color_le)
            self.tabs.addTab(self.logo_tab, "Logo / Display")

            # Colors tab (ascii_colors)
            self.colors_tab = QWidget()
            cf = QFormLayout(); self.colors_tab.setLayout(cf)
            self.ascii_colors_le = QLineEdit(); self.ascii_colors_le.setPlaceholderText("e.g. 4 6 1 3 5 or red blue")
            cf.addRow(QLabel("ASCII colors (space or comma separated)"), self.ascii_colors_le)
            self.tabs.addTab(self.colors_tab, "Colors")

            # Raw tab
            self.raw_tab = QWidget()
            rl = QVBoxLayout(); self.raw_tab.setLayout(rl)
            rl.addWidget(QLabel("Raw config (advanced). Overwrites file on save. Backup created."))
            self.raw_edit = QTextEdit()
            rl.addWidget(self.raw_edit)
            self.tabs.addTab(self.raw_tab, "Raw")

            # populate UI
            self._populate_ui()

        def _populate_ui(self):
            model = self.fast_model if self.mode == "fastfetch" else self.neo_model

            # Modules / Info
            self._refresh_items()

            # ASCII fields
            if isinstance(model, FastfetchJSONModel):
                self.backend_le.setText("")  # fastfetch uses modules; mode handled by modules
                self.ascii_distro_le.setText(model.get("ascii_distro", "") or "")
                self.ascii_file_le.setText(str(model.get("ascii_path", "") or ""))
                self.ascii_bold_cb.setChecked(bool(model.get("ascii_bold", False)))
                # colors
                colors = model.get("ascii_colors", [])
                if isinstance(colors, list):
                    self.ascii_colors_le.setText(" ".join(map(str, colors)))
                else:
                    self.ascii_colors_le.setText(str(colors))
                # logo/display
                logo = model.get("logo", {}) or {}
                if isinstance(logo, dict):
                    self.logo_type_le.setText(str(logo.get("type", "")))
                    self.logo_source_le.setText(str(logo.get("source", "")))
                else:
                    self.logo_type_le.setText("")
                    self.logo_source_le.setText("")
                self.display_title_color_le.setText(str(model.get("display", {}).get("color", {}).get("title", "") if model.get("display") else ""))
                # raw: prefer raw_text so comments visible; if absent show pretty JSON
                if getattr(model, "raw_text", ""):
                    self.raw_edit.setPlainText(model.raw_text)
                else:
                    self.raw_edit.setPlainText(json.dumps(model.data, indent=2))
            else:
                # SimpleKeyConfig: best-effort populate
                self.backend_le.setText("")
                self.ascii_distro_le.setText(model.get("ascii_distro", "") or "")
                self.ascii_file_le.setText(model.get("ascii_path", "") or "")
                self.ascii_bold_cb.setChecked(str(model.get("ascii_bold", "")).lower() in ("1","on","true","yes"))
                self.ascii_colors_le.setText(model.get("ascii_colors", "") or "")
                self.logo_type_le.setText("")
                self.logo_source_le.setText("")
                self.display_title_color_le.setText("")
                self.raw_edit.setPlainText("".join(getattr(model, "lines", [])))

        # ----------------- modules/info helpers -----------------
        def _refresh_items(self):
            self.mods_list.clear()
            model = self.fast_model if self.mode == "fastfetch" else self.neo_model
            if isinstance(model, FastfetchJSONModel):
                items = model.list_modules()
                for i, it in enumerate(items):
                    if isinstance(it, dict):
                        preview = json.dumps(it, separators=(", ", ": "))
                    else:
                        preview = str(it)
                    li = QListWidgetItem(f"{i}: {preview}")
                    li.setData(Qt.ItemDataRole.UserRole, i)
                    self.mods_list.addItem(li)
            else:
                items = model.list_info()
                for idx, label, value, rest in items:
                    display = f"{label}  →  {value}{(' '+rest) if rest else ''}"
                    li = QListWidgetItem(display)
                    li.setData(Qt.ItemDataRole.UserRole, idx)
                    self.mods_list.addItem(li)

        def _add_item(self):
            model = self.fast_model if self.mode == "fastfetch" else self.neo_model
            if isinstance(model, FastfetchJSONModel):
                txt, ok = QInputDialog.getText(self, "Add module", "Module name (string) or JSON object:")
                if not ok or not txt.strip():
                    return
                s = txt.strip()
                try:
                    if s.startswith("{"):
                        val = json.loads(s)
                    else:
                        val = s
                    model.append_module(val)
                    model.save(backup=False)
                    model.load()
                    QMessageBox.information(self, "Added", "Module added.")
                    self._populate_ui()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Invalid module: {e}")
            else:
                lbl, ok = QInputDialog.getText(self, "Info label", "Label (visible):")
                if not ok: return
                tok, ok = QInputDialog.getText(self, "Info token", "Token (distro, kernel, uptime, etc):")
                if not ok: return
                model.append_info(lbl.strip(), tok.strip())
                model.save(backup=False)
                model.load()
                QMessageBox.information(self, "Added", "Info appended.")
                self._populate_ui()

        def _edit_item(self):
            it = self.mods_list.currentItem()
            if not it:
                QMessageBox.information(self, "Select", "Select an item.")
                return
            idx = it.data(Qt.ItemDataRole.UserRole)
            model = self.fast_model if self.mode == "fastfetch" else self.neo_model
            if isinstance(model, FastfetchJSONModel):
                cur = model.list_modules()[idx]
                txt = json.dumps(cur, indent=2) if isinstance(cur, dict) else str(cur)
                new_txt, ok = QInputDialog.getMultiLineText(self, "Edit module", "Edit (string or JSON):", txt)
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
                    QMessageBox.critical(self, "Error", f"Could not update: {e}")
            else:
                items = model.list_info()
                for (i, label, value, rest) in items:
                    if i == idx:
                        orig = (i, label, value, rest)
                        break
                else:
                    QMessageBox.critical(self, "Error", "Could not find line.")
                    return
                new_label, ok = QInputDialog.getText(self, "Label", "Label:", text=orig[1])
                if not ok: return
                new_value, ok = QInputDialog.getText(self, "Token", "Token:", text=orig[2])
                if not ok: return
                model.set_info_line(idx, new_label.strip(), new_value.strip(), orig[3])
                model.save(backup=False)
                model.load()
                QMessageBox.information(self, "Saved", "Info updated.")
                self._populate_ui()

        def _remove_item(self):
            it = self.mods_list.currentItem()
            if not it:
                QMessageBox.information(self, "Select", "Select an item.")
                return
            idx = it.data(Qt.ItemDataRole.UserRole)
            model = self.fast_model if self.mode == "fastfetch" else self.neo_model
            conf = QMessageBox.question(self, "Confirm", "Remove selected item?")
            if conf != QMessageBox.StandardButton.Yes:
                return
            ok = model.remove_module(idx) if isinstance(model, FastfetchJSONModel) else model.remove_line(idx)
            if not ok:
                QMessageBox.critical(self, "Remove failed", "Failed to remove.")
                return
            model.save(backup=False)
            model.load()
            QMessageBox.information(self, "Removed", "Item removed.")
            self._populate_ui()

        # ----------------- ASCII browse -----------------
        def _browse_ascii_file(self):
            dlg = QFileDialog(self, "Select ASCII file")
            dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
            dlg.setNameFilter("Text files (*.txt *.asc *.ansi);;All files (*)")
            if dlg.exec():
                files = dlg.selectedFiles()
                if files:
                    self.ascii_file_le.setText(files[0])

        # ----------------- Save handler -----------------
        def _on_save(self):
            model = self.fast_model if self.mode == "fastfetch" else self.neo_model

            # If JSON model: write ascii_path, ascii_colors, ascii_bold, logo/display, modules preserved
            if isinstance(model, FastfetchJSONModel):
                # ascii_path
                ascii_path = self.ascii_file_le.text().strip()
                if ascii_path:
                    model.set("ascii_path", ascii_path)
                # ascii_bold
                model.set("ascii_bold", bool(self.ascii_bold_cb.isChecked()))
                # ascii_colors
                raw = self.ascii_colors_le.text().strip()
                if raw:
                    parts = [p for p in re.split(r'[,\s]+', raw) if p]
                    model.set("ascii_colors", parts)
                # ascii_distro (some users store this)
                ad = self.ascii_distro_le.text().strip()
                if ad:
                    model.set("ascii_distro", ad)
                # logo
                ltype = self.logo_type_le.text().strip()
                lsrc = self.logo_source_le.text().strip()
                if ltype or lsrc:
                    logo = model.get("logo", {}) or {}
                    if ltype:
                        logo["type"] = ltype
                    if lsrc:
                        logo["source"] = lsrc
                    model.set("logo", logo)
                # display title color
                title_col = self.display_title_color_le.text().strip()
                if title_col:
                    disp = model.get("display", {}) or {}
                    color = disp.get("color", {}) or {}
                    color["title"] = title_col
                    disp["color"] = color
                    model.set("display", disp)

                # Raw tab: if user edited raw and it's different, ask whether to overwrite whole file
                raw_txt = self.raw_edit.toPlainText()
                if raw_txt.strip() and raw_txt.strip() != (model.raw_text or "").strip():
                    resp = QMessageBox.question(self, "Raw changed", "Raw text differs from parsed JSON. Overwrite config file with Raw content? (Yes = overwrite, No = write structured changes)", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
                    if resp == QMessageBox.StandardButton.Cancel:
                        return
                    if resp == QMessageBox.StandardButton.Yes:
                        # write raw directly (backup)
                        try:
                            model._backup()
                            model.path.write_text(raw_txt + ("\n" if not raw_txt.endswith("\n") else ""), encoding="utf-8", errors="surrogateescape")
                            QMessageBox.information(self, "Saved", f"Wrote raw content to {model.path}")
                            model.load()
                            self._populate_ui()
                            return
                        except PermissionError:
                            QMessageBox.critical(self, "Permission denied", "Failed to write raw file (permission denied).")
                            return
                        except Exception as e:
                            QMessageBox.critical(self, "Save failed", f"Failed to write raw file: {e}")
                            return
                # structured save
                try:
                    model.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved {model.path}")
                    model.load()
                    self._populate_ui()
                except PermissionError:
                    QMessageBox.critical(self, "Permission denied", "Failed to save: permission denied (system file?)")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return

            # SimpleKeyConfig (neofetch) branch: best-effort writes
            missing = []
            if not model.set_existing("ascii_path", self.ascii_file_le.text().strip()):
                missing.append(("ascii_path", self.ascii_file_le.text().strip()))
            if not model.set_existing("ascii_colors", self.ascii_colors_le.text().strip()):
                # try alternate names
                if not model.set_existing("ascii_colors", self.ascii_colors_le.text().strip()):
                    missing.append(("ascii_colors", self.ascii_colors_le.text().strip()))
            # logo & display best-effort
            if self.logo_type_le.text().strip() and not model.set_existing("logo_type", self.logo_type_le.text().strip()):
                missing.append(("logo_type", self.logo_type_le.text().strip()))
            # handle missing -> ask to append
            if missing:
                msg = "Some keys were not found and would be appended:\n"
                for k, v in missing:
                    msg += f" - {k} = {v}\n"
                msg += "\nAppend them?"
                resp = QMessageBox.question(self, "Append missing", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
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
