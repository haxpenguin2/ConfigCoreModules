# plugin.py — NetworkManager config editor plugin (safe, preserves formatting)
import os
import re
import shutil
from pathlib import Path
from datetime import datetime

# Candidate locations (user-level first, then system)
NM_PATH_CANDIDATES = [
    os.path.expanduser("~/.config/NetworkManager/NetworkManager.conf"),
    "/etc/NetworkManager/NetworkManager.conf",
]

def find_nm_path():
    for p in NM_PATH_CANDIDATES:
        if os.path.isfile(p):
            return p
    # default to user config path
    return NM_PATH_CANDIDATES[0]

class NetworkManagerConfig:
    """
    INI-like editor that preserves file layout, comments and whitespace.
    Methods:
      - load()
      - get(section, key, default=None)
      - set_existing(section, key, value) -> bool (True if replaced)
      - append_key(section, key, value) -> True
      - append_section(section, mapping) -> True
      - save(backup=True)
    """
    SECTION_RE = re.compile(r'^\s*\[([^\]]+)\]\s*$')
    KEY_RE_TEMPLATE = r'^(\s*{key}\s*=\s*)(.*?)(\s*(?:[;#].*)?)$'  # captures left, value, trailing comment
    def __init__(self, path=None):
        self.path = Path(path or find_nm_path())
        self.lines = []
        self.load()

    def load(self):
        if self.path.exists():
            raw = self.path.read_text(encoding="utf-8", errors="surrogateescape")
            self.lines = raw.splitlines(True)
        else:
            # start with an empty file with a trailing newline
            self.lines = ["\n"]
        # normalize: ensure every line ends with newline
        self.lines = [ln if ln.endswith("\n") else ln + "\n" for ln in self.lines]

    def _find_section_bounds(self, section: str):
        """
        Return (start_idx, end_idx) for lines inside section (inclusive start header index, exclusive end index).
        If section not found return (None, None).
        """
        header_pat = re.compile(r'^\s*\[' + re.escape(section) + r'\]\s*$', re.IGNORECASE)
        start = None
        for i, ln in enumerate(self.lines):
            if header_pat.match(ln.strip()):
                start = i
                break
        if start is None:
            return None, None
        # end is index of next section header or len(lines)
        end = len(self.lines)
        for j in range(start + 1, len(self.lines)):
            if self.SECTION_RE.match(self.lines[j]):
                end = j
                break
        return start, end

    def _find_key_in_range(self, key: str, start_idx: int, end_idx: int):
        """
        Return index of line containing key within [start_idx+1, end_idx-1] (i.e., inside section),
        or None if not found.
        """
        pat = re.compile(self.KEY_RE_TEMPLATE.format(key=re.escape(key)), re.IGNORECASE)
        for i in range(start_idx + 1, end_idx):
            ln = self.lines[i]
            if pat.match(ln):
                return i
        return None

    def get(self, section: str, key: str, default=None):
        """
        Fetch value for section.key (case-insensitive). Returns raw string without surrounding quotes.
        """
        sstart, send = self._find_section_bounds(section)
        if sstart is None:
            return default
        idx = self._find_key_in_range(key, sstart, send)
        if idx is None:
            return default
        pat = re.compile(self.KEY_RE_TEMPLATE.format(key=re.escape(key)), re.IGNORECASE)
        m = pat.match(self.lines[idx])
        if not m:
            return default
        val = m.group(2).strip()
        # remove surrounding quotes if present
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            return val[1:-1]
        return val

    def set_existing(self, section: str, key: str, value) -> bool:
        """
        Replace existing key's value token only. Returns True if replaced, False if key/section not present.
        """
        sstart, send = self._find_section_bounds(section)
        if sstart is None:
            return False
        idx = self._find_key_in_range(key, sstart, send)
        if idx is None:
            return False
        # preserve left spacing and trailing comments
        pat = re.compile(self.KEY_RE_TEMPLATE.format(key=re.escape(key)))
        ln = self.lines[idx]
        m = pat.match(ln)
        if not m:
            # fallback: overwrite the line
            new_val = self._format_value(value)
            self.lines[idx] = f"{key} = {new_val}\n"
            return True
        left = m.group(1)
        trailing = m.group(3) or ""
        # format value: keep booleans and numbers bare, quote others
        val_text = self._format_value(value)
        # ensure trailing ends with newline
        if not trailing.endswith("\n"):
            trailing = trailing + "\n"
        self.lines[idx] = f"{left}{val_text}{trailing}"
        return True

    def _format_value(self, v):
        # Similar rules to picom plugin: booleans -> true/false (lower), numbers bare, quoted strings preserved
        if isinstance(v, bool):
            return "true" if v else "false"
        s = str(v).strip()
        if s.lower() in ("true", "false"):
            return s.lower()
        # numeric?
        try:
            int(s)
            return s
        except Exception:
            try:
                float(s)
                return s
            except Exception:
                pass
        # keep if already quoted
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s
        # else quote
        return f'"{s}"'

    def append_key(self, section: str, key: str, value):
        """
        Append key=value to an existing section (before next section header). If section missing -> False.
        """
        sstart, send = self._find_section_bounds(section)
        if sstart is None:
            return False
        # insert before send (which is start of next section or len)
        val_text = self._format_value(value)
        line = f"{key} = {val_text}\n"
        # if previous line before insertion isn't blank, add a blank line for readability
        insert_at = send
        if insert_at > 0 and not self.lines[insert_at - 1].strip():
            # already blank above insertion point, okay
            pass
        else:
            # insert a blank line before new keys for neatness
            self.lines.insert(insert_at, "\n")
            insert_at += 1
        self.lines.insert(insert_at, line)
        return True

    def append_section(self, section: str, mapping: dict):
        """
        Append an entire new [section] at the end of file (with a blank line).
        """
        if not self.lines or not self.lines[-1].endswith("\n"):
            self.lines.append("\n")
        # ensure a blank line before a new section
        if len(self.lines) >= 1 and self.lines[-1].strip() != "":
            self.lines.append("\n")
        self.lines.append(f"[{section}]\n")
        for k, v in mapping.items():
            val_text = self._format_value(v)
            self.lines.append(f"{k} = {val_text}\n")
        return True

    def save(self, backup: bool = True):
        if backup and self.path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = self.path.with_suffix(self.path.suffix + f".bak.{ts}")
            try:
                shutil.copy2(self.path, bak)
            except Exception:
                # ignore backup failure, we'll still try to save
                pass
        # ensure parent exists for user-level files
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8", errors="surrogateescape") as f:
                f.writelines(self.lines)
        except Exception as e:
            # re-raise so UI can alert user about permission issues
            raise

# Lazy UI factory
def create_editor(core_config=None):
    # Lazy imports to avoid Qt dependency at import-time
    try:
        from PyQt6.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QLineEdit, QCheckBox, QPushButton,
            QMessageBox, QHBoxLayout, QComboBox, QGroupBox, QFormLayout
        )
        from PyQt6.QtCore import Qt
    except Exception:
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QLineEdit, QCheckBox, QPushButton,
            QMessageBox, QHBoxLayout, QComboBox, QGroupBox, QFormLayout
        )
        from PyQt5.QtCore import Qt

    class NMEditor(QWidget):
        def __init__(self, *_):
            super().__init__()
            self.cfg = NetworkManagerConfig(find_nm_path())
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout()
            self.setLayout(layout)
            layout.addWidget(QLabel(f"Editing: {self.cfg.path}"))

            # Main section group
            main_g = QGroupBox("[main]")
            main_form = QFormLayout()
            main_g.setLayout(main_form)
            self.plugins_le = QLineEdit()
            self.plugins_le.setPlaceholderText("e.g. keyfile,ifcfg-rh")
            try:
                cur_plugins = self.cfg.get("main", "plugins", "")
                if cur_plugins is not None:
                    self.plugins_le.setText(cur_plugins)
            except Exception:
                pass
            main_form.addRow(QLabel("plugins"), self.plugins_le)
            layout.addWidget(main_g)

            # ifupdown section
            if_g = QGroupBox("[ifupdown]")
            if_form = QFormLayout()
            if_g.setLayout(if_form)
            self.if_managed_cb = QCheckBox("managed (ifupdown)")
            cur_managed = self.cfg.get("ifupdown", "managed", None)
            if cur_managed is not None:
                self.if_managed_cb.setChecked(str(cur_managed).strip().lower() == "true")
            if_form.addRow(self.if_managed_cb)
            layout.addWidget(if_g)

            # logging section
            log_g = QGroupBox("[logging]")
            log_form = QFormLayout()
            log_g.setLayout(log_form)
            self.log_level_cb = QComboBox()
            self.log_level_cb.addItems(["WARN", "INFO", "DEBUG"])
            cur_level = self.cfg.get("logging", "level", "")
            if cur_level:
                # normalize
                cur_level_clean = cur_level.strip().upper().strip('"').strip("'")
                idx = self.log_level_cb.findText(cur_level_clean)
                if idx >= 0:
                    self.log_level_cb.setCurrentIndex(idx)
            log_form.addRow(QLabel("level"), self.log_level_cb)
            layout.addWidget(log_g)

            # Save button
            row = QHBoxLayout()
            save_btn = QPushButton("Save (safe)")
            save_btn.clicked.connect(self._on_save)
            row.addWidget(save_btn)
            layout.addLayout(row)

        def _on_save(self):
            missing = []
            # attempt to set existing keys; collect missing
            if not self.cfg.set_existing("main", "plugins", self.plugins_le.text().strip()):
                missing.append(("section", "main", {"plugins": self.plugins_le.text().strip()}))
            # ifupdown managed
            val = "true" if self.if_managed_cb.isChecked() else "false"
            if not self.cfg.set_existing("ifupdown", "managed", val):
                missing.append(("section", "ifupdown", {"managed": val}))
            # logging.level
            lv = self.log_level_cb.currentText()
            if not self.cfg.set_existing("logging", "level", lv):
                missing.append(("section", "logging", {"level": lv}))

            # If nothing missing, just save
            if not missing:
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved {self.cfg.path}")
                except PermissionError:
                    QMessageBox.critical(self, "Permission denied",
                        f"Failed to save {self.cfg.path}. You may need to run the editor with elevated privileges to edit system files (e.g. /etc/NetworkManager/NetworkManager.conf).")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return

            # Prompt user about appending missing sections/keys
            msg = "Some sections or keys were not found in your NetworkManager.conf. By default the editor only edits existing keys.\n\nMissing items:\n"
            for typ, sect, mapping in missing:
                msg += f" - [{sect}]: {', '.join(f'{k}={v}' for k, v in mapping.items())}\n"
            msg += "\nAppend the missing sections/keys? (No = save only existing changes)\n\nNote: writing to system paths like /etc may require elevated permissions."
            resp = QMessageBox.question(self, "Missing keys/sections", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if resp == QMessageBox.StandardButton.Cancel:
                # treat as "save current existing changes" (as Picom does)
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved existing-key changes to {self.cfg.path}")
                except PermissionError:
                    QMessageBox.critical(self, "Permission denied",
                        f"Failed to save {self.cfg.path}. You may need elevated privileges.")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return
            if resp == QMessageBox.StandardButton.No:
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved existing-key changes to {self.cfg.path}")
                except PermissionError:
                    QMessageBox.critical(self, "Permission denied",
                        f"Failed to save {self.cfg.path}. You may need elevated privileges.")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return

            # Yes -> append missing things
            for _, sect, mapping in missing:
                sstart, send = self.cfg._find_section_bounds(sect)
                if sstart is None:
                    # create new section
                    self.cfg.append_section(sect, mapping)
                else:
                    # append keys into existing section
                    for k, v in mapping.items():
                        self.cfg.append_key(sect, k, v)
            try:
                self.cfg.save(backup=True)
                QMessageBox.information(self, "Saved", f"Saved (with appended items) to {self.cfg.path}")
            except PermissionError:
                QMessageBox.critical(self, "Permission denied",
                    f"Failed to save {self.cfg.path}. You may need elevated privileges (e.g. write to /etc requires root).")
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")

    return NMEditor(core_config)
