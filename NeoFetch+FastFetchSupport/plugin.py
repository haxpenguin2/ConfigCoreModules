# plugin.py — Combined fastfetch / neofetch config editor plugin
# - Detects ~/.config/fastfetch/config and ~/.config/neofetch/config.conf (and common alternates)
# - Multi-tab UI: General / ASCII & Image / Info Items / Colors / Raw
# - Safe edits: replace only tokens when possible, append with consent, preserve comments/whitespace
import os
import re
import shutil
from pathlib import Path
from datetime import datetime

# Candidate config paths
FASTFETCH_PATHS = [
    os.path.expanduser("~/.config/fastfetch/config"),
    os.path.expanduser("~/.fastfetch/config"),
]
NEOFETCH_PATHS = [
    os.path.expanduser("~/.config/neofetch/config.conf"),
    os.path.expanduser("~/.config/neofetch/config"),
    os.path.expanduser("~/.neofetch/config.conf"),
]

def first_existing(paths):
    for p in paths:
        if os.path.isfile(p):
            return p
    return paths[0]  # default choice (user may create later)

class SimpleKeyConfig:
    """
    Generic conservative editor for simple key=value style config files (fastfetch/neofetch common case).
    - Preserves lines, comments, whitespace
    - get(key) returns raw string (unquoted)
    - set_existing(key, value) replaces first occurrence, returns True if replaced
    - append_key(key, value) appends at EOF
    - supports "arrays" written like: ascii_colors=(1 2 3) by writing raw string
    - supports special lines like: info "Label" distro  (managed separately)
    """
    # match key = "value"  OR key="value" OR key = value OR key=value OR key=(...) ; captures left, value, trailing comment
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
        # reuse KEY_RE to extract val
        pat = re.compile(self.KEY_RE.pattern.format(key=re.escape(key)))
        m = pat.match(ln)
        if not m:
            return default
        val = m.groupdict().get("val")
        if val is None:
            return ""  # flag present with no explicit value
        val = val.strip()
        # remove surrounding quotes
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            return val[1:-1]
        return val

    def set_existing(self, key, value) -> bool:
        """
        Replace value token only. Return True if replaced, False if key not found.
        value should be a string as desired in the file (no extra quoting added except common cases).
        """
        idx = self._find_key_idx(key)
        if idx is None:
            return False
        ln = self.lines[idx]
        pat = re.compile(self.KEY_RE.pattern.format(key=re.escape(key)))
        m = pat.match(ln)
        if not m:
            # fallback: overwrite entire line
            self.lines[idx] = f"{key} = {value}\n"
            return True
        left = m.group(1)
        comment = m.groupdict().get("comment") or ""
        # ensure newline on comment part
        if comment and not comment.endswith("\n"):
            comment = comment + "\n"
        # keep value as-is; add quotes if value contains spaces and is not an array or already quoted
        val_text = value
        if " " in val_text and not (val_text.startswith("(") and val_text.endswith(")")) and not ((val_text.startswith('"') and val_text.endswith('"')) or (val_text.startswith("'") and val_text.endswith("'"))):
            val_text = f'"{val_text}"'
        self.lines[idx] = f"{left}= {val_text}{comment}"
        return True

    def append_key(self, key, value):
        if not self.lines or not self.lines[-1].endswith("\n"):
            self.lines.append("\n")
        # ensure blank line separation
        if len(self.lines) >= 1 and self.lines[-1].strip() != "":
            self.lines.append("\n")
        val_text = value
        if " " in val_text and not (val_text.startswith("(") and val_text.endswith(")")) and not ((val_text.startswith('"') and val_text.endswith('"')) or (val_text.startswith("'") and val_text.endswith("'"))):
            val_text = f'"{val_text}"'
        self.lines.append(f"{key}={val_text}\n")
        return True

    # Info lines (fastfetch/neofetch often include info lines like: info "OS" distro)
    def list_info(self):
        items = []
        for i, ln in enumerate(self.lines):
            m = self.INFO_RE.match(ln)
            if m:
                label = m.group("label").strip()
                value = m.group("value").strip()
                rest = m.group("rest") or ""
                # strip quotes for label
                if (label.startswith('"') and label.endswith('"')) or (label.startswith("'") and label.endswith("'")):
                    label = label[1:-1]
                items.append((i, label, value, rest.rstrip("\n")))
        return items

    def append_info(self, label, value):
        # produce: info "Label" value
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

# ---------------- Lazy UI factory ----------------
def create_editor(core_config=None):
    try:
        from PyQt6.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QPushButton, QTabWidget, QLineEdit,
            QHBoxLayout, QMessageBox, QListWidget, QListWidgetItem, QComboBox,
            QTextEdit, QGroupBox, QFormLayout, QSpinBox, QCheckBox
        )
        from PyQt6.QtCore import Qt
    except Exception:
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QPushButton, QTabWidget, QLineEdit,
            QHBoxLayout, QMessageBox, QListWidget, QListWidgetItem, QComboBox,
            QTextEdit, QGroupBox, QFormLayout, QSpinBox, QCheckBox
        )
        from PyQt5.QtCore import Qt

    class FetchEditor(QWidget):
        def __init__(self, *_):
            super().__init__()
            # choose config files
            self.fast_path = first_existing(FASTFETCH_PATHS)
            self.neofetch_path = first_existing(NEOFETCH_PATHS)
            self.fast_exists = os.path.isfile(self.fast_path)
            self.neofetch_exists = os.path.isfile(self.neofetch_path)

            # Default to existing one or fastfetch if neither exists
            self.current_mode = "fastfetch" if self.fast_exists else ("neofetch" if self.neofetch_exists else "fastfetch")
            self._load_models()
            self._build_ui()

        def _load_models(self):
            self.models = {}
            self.models["fastfetch"] = SimpleKeyConfig(self.fast_path)
            self.models["neofetch"] = SimpleKeyConfig(self.neofetch_path)

        def _build_ui(self):
            layout = QVBoxLayout()
            self.setLayout(layout)
            header = QHBoxLayout()
            header.addWidget(QLabel("Editing:"))
            self.mode_combo = QComboBox()
            self.mode_combo.addItems(["fastfetch", "neofetch"])
            self.mode_combo.setCurrentText(self.current_mode)
            self.mode_combo.currentTextChanged.connect(self._on_mode_change)
            header.addWidget(self.mode_combo)
            header.addStretch()
            save_btn = QPushButton("Save (safe)")
            save_btn.clicked.connect(self._on_save)
            header.addWidget(save_btn)
            layout.addLayout(header)

            self.tabs = QTabWidget()
            layout.addWidget(self.tabs)

            # General tab
            self.general_tab = QWidget()
            g_layout = QFormLayout()
            self.general_tab.setLayout(g_layout)
            self.title_le = QLineEdit(); self.title_le.setPlaceholderText("Title shown at top (e.g. 'My System')")
            self.align_cb = QComboBox(); self.align_cb.addItems(["left", "center", "right"])
            self.gap_spin = QSpinBox(); self.gap_spin.setRange(0, 10)
            self.show_batt_cb = QCheckBox("Show battery")
            self.show_disk_cb = QCheckBox("Show disk")
            self.show_pkg_cb = QCheckBox("Show packages")
            g_layout.addRow(QLabel("Title"), self.title_le)
            g_layout.addRow(QLabel("Align"), self.align_cb)
            g_layout.addRow(QLabel("Gap (space between art and info)"), self.gap_spin)
            g_layout.addRow(self.show_batt_cb)
            g_layout.addRow(self.show_disk_cb)
            g_layout.addRow(self.show_pkg_cb)
            self.tabs.addTab(self.general_tab, "General")

            # ASCII / Image tab
            self.ascii_tab = QWidget()
            a_layout = QFormLayout()
            self.ascii_tab.setLayout(a_layout)
            self.image_backend_cb = QComboBox()
            self.image_backend_cb.addItems(["ascii", "image", "off"])
            self.ascii_distro_le = QLineEdit(); self.ascii_distro_le.setPlaceholderText("Distro for ASCII art (e.g. Arch)")
            self.ascii_file_le = QLineEdit(); self.ascii_file_le.setPlaceholderText("/path/to/image or logo")
            a_layout.addRow(QLabel("Mode (ascii/image/off)"), self.image_backend_cb)
            a_layout.addRow(QLabel("ASCII distro (ascii art)"), self.ascii_distro_le)
            a_layout.addRow(QLabel("Image file (for image mode)"), self.ascii_file_le)
            self.tabs.addTab(self.ascii_tab, "ASCII / Image")

            # Info Items tab
            self.info_tab = QWidget()
            info_layout = QVBoxLayout()
            self.info_tab.setLayout(info_layout)
            info_layout.addWidget(QLabel("Info items (order matters). These show the left/right 'info' lines."))
            self.info_list = QListWidget()
            info_layout.addWidget(self.info_list)
            info_row = QHBoxLayout()
            add_info_btn = QPushButton("Add")
            add_info_btn.clicked.connect(self._add_info)
            edit_info_btn = QPushButton("Edit")
            edit_info_btn.clicked.connect(self._edit_info)
            rm_info_btn = QPushButton("Remove")
            rm_info_btn.clicked.connect(self._remove_info)
            refresh_info_btn = QPushButton("Refresh")
            refresh_info_btn.clicked.connect(self._refresh_info)
            info_row.addWidget(add_info_btn); info_row.addWidget(edit_info_btn); info_row.addWidget(rm_info_btn); info_row.addWidget(refresh_info_btn)
            info_layout.addLayout(info_row)
            self.tabs.addTab(self.info_tab, "Info Items")

            # Colors tab
            self.colors_tab = QWidget()
            c_layout = QFormLayout()
            self.colors_tab.setLayout(c_layout)
            self.ascii_colors_le = QLineEdit(); self.ascii_colors_le.setPlaceholderText("e.g. 4 6 1 3 5  (space-separated color indices)")
            self.color_blocks_cb = QCheckBox("Show color blocks")
            c_layout.addRow(QLabel("ASCII color indices"), self.ascii_colors_le)
            c_layout.addRow(self.color_blocks_cb)
            self.tabs.addTab(self.colors_tab, "Colors")

            # Raw tab (full text)
            self.raw_tab = QWidget()
            r_layout = QVBoxLayout()
            self.raw_tab.setLayout(r_layout)
            self.raw_edit = QTextEdit()
            r_layout.addWidget(QLabel("Raw configuration (advanced). Edits here overwrite the file (backup created)."))
            r_layout.addWidget(self.raw_edit)
            self.tabs.addTab(self.raw_tab, "Raw")

            # load values into UI
            self._populate_ui()

        def _on_mode_change(self, txt):
            self.current_mode = txt
            self._populate_ui()

        def _populate_ui(self):
            model = self.models[self.current_mode]
            # General
            title = model.get("title", "")
            self.title_le.setText(title or "")
            align = model.get("align", "left")
            idx = self.align_cb.findText(align)
            if idx >= 0:
                self.align_cb.setCurrentIndex(idx)
            gap = model.get("gap", "3")
            try:
                self.gap_spin.setValue(int(gap))
            except Exception:
                self.gap_spin.setValue(3)
            # show flags: try common keys
            sb = model.get("show_battery", model.get("show_batt", model.get("show_batt","")))
            self.show_batt_cb.setChecked(str(sb).strip().lower() in ("1","on","true","yes"))
            sd = model.get("show_disk", "")
            self.show_disk_cb.setChecked(str(sd).strip().lower() in ("1","on","true","yes"))
            sp = model.get("show_packages", "")
            self.show_pkg_cb.setChecked(str(sp).strip().lower() in ("1","on","true","yes"))

            # ASCII / image
            backend = model.get("image_backend", model.get("image_backend", model.get("image","ascii")))
            # normalize some names
            if backend in ("ascii","image","off"):
                self.image_backend_cb.setCurrentText(backend)
            else:
                # heuristics: neofetch uses 'ascii' and 'image' modes; fastfetch uses 'ascii' by default
                self.image_backend_cb.setCurrentText("ascii")
            self.ascii_distro_le.setText(model.get("ascii_distro", ""))
            self.ascii_file_le.setText(model.get("image_file", model.get("image_source", "")))

            # Info list
            self._refresh_info()

            # Colors
            ac = model.get("ascii_colors", model.get("ascii_colors", ""))
            # some configs use arrays like (4 6 1) or space-separated in a string. show raw
            if isinstance(ac, str):
                self.ascii_colors_le.setText(ac.strip("()\"' "))
            else:
                self.ascii_colors_le.setText(str(ac))

            cb = model.get("color_blocks", model.get("color_blocks", ""))
            self.color_blocks_cb.setChecked(str(cb).strip().lower() in ("1","on","true","yes"))

            # Raw
            self.raw_edit.setPlainText("".join(model.lines))

        # ---------- Info list helpers ----------
        def _refresh_info(self):
            self.info_list.clear()
            model = self.models[self.current_mode]
            items = model.list_info()
            for idx, label, value, rest in items:
                display = f"{label}  →  {value}{(' '+rest) if rest else ''}"
                it = QListWidgetItem(display)
                it.setData(Qt.ItemDataRole.UserRole, idx)
                self.info_list.addItem(it)

        def _add_info(self):
            # simple dialog sequence (QInputDialog fallback avoided for minimal imports)
            from PyQt6.QtWidgets import QInputDialog
            label, ok = QInputDialog.getText(self, "Info label", "Label (visible name):")
            if not ok:
                return
            value, ok = QInputDialog.getText(self, "Info value", "Value token (e.g. distro, kernel, uptime, memory, cpu):")
            if not ok:
                return
            model = self.models[self.current_mode]
            model.append_info(label.strip(), value.strip())
            QMessageBox.information(self, "Added", "Info item appended.")
            model.save(backup=False)  # save quick so raw updates
            model.load()
            self._populate_ui()

        def _edit_info(self):
            it = self.info_list.currentItem()
            if not it:
                QMessageBox.information(self, "Select", "Select an info item to edit.")
                return
            idx = it.data(Qt.ItemDataRole.UserRole)
            model = self.models[self.current_mode]
            # fetch original
            items = model.list_info()
            for (i, label, value, rest) in items:
                if i == idx:
                    orig_label, orig_value, orig_rest = label, value, rest
                    break
            else:
                QMessageBox.critical(self, "Error", "Couldn't find info line.")
                return
            from PyQt6.QtWidgets import QInputDialog
            new_label, ok = QInputDialog.getText(self, "Edit label", "Label:", text=orig_label)
            if not ok:
                return
            new_value, ok = QInputDialog.getText(self, "Edit value token", "Value token:", text=orig_value)
            if not ok:
                return
            model.set_info_line(idx, new_label.strip(), new_value.strip(), orig_rest)
            QMessageBox.information(self, "Saved", "Info line updated.")
            model.save(backup=False)
            model.load()
            self._populate_ui()

        def _remove_info(self):
            it = self.info_list.currentItem()
            if not it:
                QMessageBox.information(self, "Select", "Select an info item to remove.")
                return
            idx = it.data(Qt.ItemDataRole.UserRole)
            model = self.models[self.current_mode]
            confirm = QMessageBox.question(self, "Confirm remove", "Remove selected info line?")
            if confirm != QMessageBox.StandardButton.Yes:
                return
            if not model.remove_line(idx):
                QMessageBox.critical(self, "Remove failed", "Failed to remove the line.")
                return
            model.save(backup=False)
            model.load()
            self._populate_ui()

        # ---------- Save handling ----------
        def _on_save(self):
            model = self.models[self.current_mode]
            missing = []

            # General options
            title = self.title_le.text().strip()
            if title:
                if not model.set_existing("title", title):
                    missing.append(("title", title))
            align = self.align_cb.currentText()
            if not model.set_existing("align", align):
                missing.append(("align", align))
            gap = str(self.gap_spin.value())
            if not model.set_existing("gap", gap):
                missing.append(("gap", gap))
            # flags
            if not model.set_existing("show_battery", "on" if self.show_batt_cb.isChecked() else "off"):
                # try alternate key names
                if not model.set_existing("show_batt", "on" if self.show_batt_cb.isChecked() else "off"):
                    missing.append(("show_battery", "on" if self.show_batt_cb.isChecked() else "off"))
            if not model.set_existing("show_disk", "on" if self.show_disk_cb.isChecked() else "off"):
                missing.append(("show_disk", "on" if self.show_disk_cb.isChecked() else "off"))
            if not model.set_existing("show_packages", "on" if self.show_pkg_cb.isChecked() else "off"):
                missing.append(("show_packages", "on" if self.show_pkg_cb.isChecked() else "off"))

            # ASCII/Image
            backend = self.image_backend_cb.currentText()
            if not model.set_existing("image_backend", backend):
                # some configs use "image" or "ascii" differently; attempt common alt keys
                if not model.set_existing("image", backend):
                    missing.append(("image_backend", backend))
            if not model.set_existing("ascii_distro", self.ascii_distro_le.text().strip()):
                if not model.set_existing("ascii", self.ascii_distro_le.text().strip()):
                    missing.append(("ascii_distro", self.ascii_distro_le.text().strip()))
            if not model.set_existing("image_file", self.ascii_file_le.text().strip()):
                # alt key names used in fastfetch/neofetch vary; we'll try a few
                tried = False
                for alt in ("image_source", "image_path", "image_file"):
                    if model.set_existing(alt, self.ascii_file_le.text().strip()):
                        tried = True
                        break
                if not tried:
                    missing.append(("image_file", self.ascii_file_le.text().strip()))

            # Colors
            raw_colors = self.ascii_colors_le.text().strip()
            if raw_colors:
                # write as array for fastfetch ( (1 2 3) ) and as space-separated for neofetch; user sees raw numbers
                val_to_write = f"({raw_colors})"
                if not model.set_existing("ascii_colors", val_to_write):
                    # try also plain ascii_colors without parentheses
                    if not model.set_existing("ascii_colors", raw_colors):
                        missing.append(("ascii_colors", val_to_write))
            if not model.set_existing("color_blocks", "on" if self.color_blocks_cb.isChecked() else "off"):
                missing.append(("color_blocks", "on" if self.color_blocks_cb.isChecked() else "off"))

            # If nothing missing -> save
            if not missing:
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

            # Prompt about appending missing keys
            msg = "Some keys were not found in the config. By default this editor only modifies existing keys.\n\nMissing items:\n"
            for k, v in missing:
                msg += f" - {k} = {v}\n"
            msg += "\nAppend these keys at end of file? (No = save only existing changes)\n\nNote: system files may require elevated privileges to modify."
            resp = QMessageBox.question(self, "Append missing keys?", msg,
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if resp == QMessageBox.StandardButton.Cancel:
                # treat as save existing changes
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

            # Yes -> append missing keys
            for k, v in missing:
                model.append_key(k, v)
            try:
                model.save(backup=True)
                QMessageBox.information(self, "Saved (with appended items)", f"Saved {model.path}")
                model.load()
                self._populate_ui()
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")

        # ---------- Raw save ----------
        # exposed via Raw tab Save button in the core GUI (core already provides Save). Provide small helper to write raw edits.
        # The core GUI saves by calling plugin widget methods; to keep parity we support writing raw text in this plugin via its internal model.
        def save_raw_from_widget(self):
            model = self.models[self.current_mode]
            txt = self.raw_edit.toPlainText()
            confirm = QMessageBox.question(self, "Overwrite file?",
                                           "Overwrite the config file with the raw text in this tab? (A backup will be created)")
            if confirm != QMessageBox.StandardButton.Yes:
                return
            try:
                model.lines = [ln if ln.endswith("\n") else ln + "\n" for ln in txt.splitlines(True)]
                model.save(backup=True)
                QMessageBox.information(self, "Saved", f"Saved {model.path}")
                model.load()
                self._populate_ui()
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save raw file: {e}")

    return FetchEditor(core_config)
