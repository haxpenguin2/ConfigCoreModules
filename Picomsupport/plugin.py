# plugin.py — Picom editor plugin (safe, no-escaping writes)
# Lazy-load GUI: no Qt widgets at import-time. Safe edits: replace only the value token.

import os, shutil, re
from pathlib import Path
from datetime import datetime

PICOM_PATH_CANDIDATES = [
    os.path.expanduser("~/.config/picom.conf"),
    os.path.expanduser("~/.config/pipewire/picom.conf"),
]

def find_picom_path():
    for p in PICOM_PATH_CANDIDATES:
        if os.path.isfile(p):
            return p
    return PICOM_PATH_CANDIDATES[0]

class PicomConfig:
    """
    Minimal, careful editor for picom.conf that:
      - preserves line formatting
      - replaces only the value token between '=' and ';' for existing keys
      - edits sub-keys inside blocks similarly
      - does NOT escape quotes or use repr()
      - creates timestamped backups on save
    """
    def __init__(self, path=None):
        self.path = Path(path or find_picom_path())
        self.lines = []
        self.load()

    def load(self):
        if self.path.exists():
            self.lines = self.path.read_text(encoding="utf-8").splitlines(True)
        else:
            self.lines = []
        # normalize newline endings
        self.lines = [ln if ln.endswith("\n") else ln + "\n" for ln in self.lines]

    # find line index for top-level key like "key = value;"
    def _find_top_key_idx(self, key: str):
        pat = re.compile(r'^\s*' + re.escape(key) + r'\s*=')
        for i, ln in enumerate(self.lines):
            if pat.match(ln):
                return i
        return None

    # find block header and its braces: return (header_idx, open_idx, close_idx)
    def _find_block(self, block_name: str):
        header_pat = re.compile(r'^\s*' + re.escape(block_name) + r'\s*:\s*$')
        header_idx = None; open_idx = None; close_idx = None
        for i, ln in enumerate(self.lines):
            if header_pat.match(ln):
                header_idx = i
                # find next line with { (skip blank lines)
                j = i + 1
                while j < len(self.lines) and self.lines[j].strip() == "":
                    j += 1
                if j < len(self.lines) and self.lines[j].strip().startswith("{"):
                    open_idx = j
                    # find matching closing brace
                    depth = 1
                    k = j + 1
                    while k < len(self.lines):
                        depth += self.lines[k].count("{")
                        depth -= self.lines[k].count("}")
                        if depth == 0:
                            close_idx = k
                            break
                        k += 1
                break
        return header_idx, open_idx, close_idx

    # safe formatting: do NOT escape quotes; caller may pass quoted strings if desired
    def _format_value(self, v):
        """
        Produce a picom-safe textual representation for a value **without** adding
        redundant quotes. Rules:
          - Python bools -> 'true'/'false' (no quotes)
          - Strings exactly 'true' or 'false' (case-insensitive) -> returned lowercased (no quotes)
          - Numeric-looking strings or numbers -> returned without quotes
          - Strings already quoted (start/end with " or ') -> returned unchanged
          - Otherwise wrap in double quotes
        """
        # booleans first
        if isinstance(v, bool):
            return "true" if v else "false"

        s = str(v)

        # if caller passed explicit picom literal true/false as string -> keep as bare
        if s.strip().lower() in ("true", "false"):
            return s.strip().lower()

        # keep strings already quoted
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s

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

        # default: wrap in double quotes (safe)
        return f'"{s}"'

    def get(self, key: str, default=None):
        # support block.key
        if "." in key:
            block, sub = key.split(".", 1)
            h, bo, bc = self._find_block(block)
            if bo is None or bc is None:
                return default
            sub_pat = re.compile(r'^\s*' + re.escape(sub) + r'\s*=\s*(.+);')
            for ln in self.lines[bo+1:bc]:
                m = sub_pat.match(ln)
                if m:
                    val = m.group(1).strip()
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        return val[1:-1]
                    return val
            return default
        else:
            idx = self._find_top_key_idx(key)
            if idx is None:
                return default
            m = re.match(r'^\s*' + re.escape(key) + r'\s*=\s*(.+);', self.lines[idx])
            if m:
                val = m.group(1).strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    return val[1:-1]
                return val
            return default

    def set_existing_top(self, key: str, value) -> bool:
        """
        Replace the existing top-level key's value token only.
        Return True if an existing line was modified, False if key not found.
        """
        idx = self._find_top_key_idx(key)
        if idx is None:
            return False
        val_str = self._format_value(value)
        # Replace the token between '=' and ';' preserving prefix/spaces and any trailing comment
        ln = self.lines[idx]
        # split into three parts: left (through '='), middle (value token), right (from ';' onward)
        m = re.match(r'^(\s*' + re.escape(key) + r'\s*=\s*)(.*?)(;.*)?(\n?)$', ln)
        if not m:
            # fallback: overwrite entire line safely
            self.lines[idx] = f"{key} = {val_str};\n"
            return True
        left = m.group(1)
        right = m.group(3) or ";"
        # ensure right ends with newline
        if not right.endswith("\n"):
            right = right + "\n"
        self.lines[idx] = f"{left}{val_str}{right}"
        return True

    def set_existing_block_key(self, block: str, sub: str, value) -> bool:
        """
        Replace existing sub-key inside an existing block.
        Return True if modified, False if not present.
        """
        h, bo, bc = self._find_block(block)
        if bo is None or bc is None:
            return False
        sub_pat = re.compile(r'^(\s*)' + re.escape(sub) + r'\s*=\s*(.*?)(;.*)?(\n?)$')
        for i in range(bo+1, bc):
            m = sub_pat.match(self.lines[i])
            if m:
                indent = m.group(1) or ""
                trailing = m.group(3) or ";"
                if not trailing.endswith("\n"):
                    trailing = trailing + "\n"
                val_str = self._format_value(value)
                self.lines[i] = f"{indent}{sub} = {val_str}{trailing}"
                return True
        return False

    # Append top-level key (only when user permits)
    def append_top_key(self, key: str, value):
        val_str = self._format_value(value)
        if len(self.lines) and not self.lines[-1].endswith("\n\n"):
            self.lines.append("\n")
        self.lines.append(f"{key} = {val_str};\n")
        return True

    # Append a block (only when user permits)
    def append_block(self, block: str, pairs: dict):
        if len(self.lines) and not self.lines[-1].endswith("\n\n"):
            self.lines.append("\n")
        self.lines.append(f"{block}:\n{{\n")
        for k, v in pairs.items():
            vstr = self._format_value(v)
            self.lines.append(f"    {k} = {vstr};\n")
        self.lines.append("};\n")
        return True

    def save(self, backup: bool = True):
        if backup and self.path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = self.path.with_suffix(self.path.suffix + f".bak.{ts}")
            shutil.copy2(self.path, bak)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(self.lines), encoding="utf-8")
        self.load()

# Lazy factory that builds the Qt UI only after QApplication exists
def create_editor(core_config=None):
    try:
        from PyQt6.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QComboBox, QCheckBox,
            QDoubleSpinBox, QPushButton, QHBoxLayout, QMessageBox
        )
        from PyQt6.QtCore import Qt
    except Exception:
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QComboBox, QCheckBox,
            QDoubleSpinBox, QPushButton, QHBoxLayout, QMessageBox
        )
        from PyQt5.QtCore import Qt

    class PicomEditor(QWidget):
        def __init__(self, *_):
            super().__init__()
            self.cfg = PicomConfig(find_picom_path())
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout()
            self.setLayout(layout)
            layout.addWidget(QLabel(f"Editing: {self.cfg.path}"))

            # backend
            layout.addWidget(QLabel("Backend"))
            self.backend_cb = QComboBox()
            self.backend_cb.addItems(["xrender", "glx", "xr_glx_hybrid"])
            cur_backend = self.cfg.get("backend", "glx")
            if cur_backend is None:
                cur_backend = "glx"
            self.backend_cb.setCurrentText(cur_backend)
            layout.addWidget(self.backend_cb)

            # vsync
            self.vsync_cb = QCheckBox("VSync")
            self.vsync_cb.setChecked(str(self.cfg.get("vsync", "true")).lower() == "true")
            layout.addWidget(self.vsync_cb)

            # opacities
            layout.addWidget(QLabel("Inactive opacity"))
            self.inactive = QDoubleSpinBox(); self.inactive.setRange(0.0, 1.0); self.inactive.setSingleStep(0.01)
            try: self.inactive.setValue(float(self.cfg.get("inactive-opacity", 0.7)))
            except Exception: self.inactive.setValue(0.7)
            layout.addWidget(self.inactive)

            layout.addWidget(QLabel("Active opacity"))
            self.active = QDoubleSpinBox(); self.active.setRange(0.0, 1.0); self.active.setSingleStep(0.01)
            try: self.active.setValue(float(self.cfg.get("active-opacity", 1.0)))
            except Exception: self.active.setValue(1.0)
            layout.addWidget(self.active)

            # blur block
            layout.addWidget(QLabel("Blur method (block)"))
            self.blur_method = QComboBox()
            self.blur_method.addItems(["dual_kawase", "kawase", "box", "gaussian", "none"])
            bm = self.cfg.get("blur.method", "")
            if bm:
                self.blur_method.setCurrentText(bm.strip('"').strip("'"))
            layout.addWidget(self.blur_method)

            layout.addWidget(QLabel("Blur strength"))
            self.blur_strength = QDoubleSpinBox(); self.blur_strength.setRange(0, 100); self.blur_strength.setSingleStep(1)
            try: self.blur_strength.setValue(float(self.cfg.get("blur.strength", 5)))
            except Exception: self.blur_strength.setValue(5)
            layout.addWidget(self.blur_strength)

            # shadows
            self.shadow_cb = QCheckBox("Shadow"); self.shadow_cb.setChecked(str(self.cfg.get("shadow", "true")).lower() == "true")
            layout.addWidget(self.shadow_cb)
            layout.addWidget(QLabel("Shadow opacity"))
            self.shadow_op = QDoubleSpinBox(); self.shadow_op.setRange(0.0, 1.0); self.shadow_op.setSingleStep(0.01)
            try: self.shadow_op.setValue(float(self.cfg.get("shadow-opacity", 0.25)))
            except Exception: self.shadow_op.setValue(0.25)
            layout.addWidget(self.shadow_op)

            # corner radius
            layout.addWidget(QLabel("Corner radius"))
            self.corner = QDoubleSpinBox(); self.corner.setRange(0, 200); self.corner.setSingleStep(1)
            try: self.corner.setValue(int(float(self.cfg.get("corner-radius", 10))))
            except Exception: self.corner.setValue(10)
            layout.addWidget(self.corner)

            # fading
            self.fading_cb = QCheckBox("Fading"); self.fading_cb.setChecked(str(self.cfg.get("fading","true")).lower()=="true")
            layout.addWidget(self.fading_cb)
            layout.addWidget(QLabel("Fade-in step"))
            self.fade_in = QDoubleSpinBox(); self.fade_in.setRange(0.0,1.0); self.fade_in.setSingleStep(0.01)
            try: self.fade_in.setValue(float(self.cfg.get("fade-in-step", 0.03)))
            except Exception: self.fade_in.setValue(0.03)
            layout.addWidget(self.fade_in)

            # Save button
            btn_row = QHBoxLayout()
            save_btn = QPushButton("Save (safe)")
            save_btn.clicked.connect(self._on_save)
            btn_row.addWidget(save_btn)
            layout.addLayout(btn_row)

        def _on_save(self):
            # Try to set existing keys only
            missing = []
            # top-level
            if not self.cfg.set_existing_top("backend", self.backend_cb.currentText()):
                missing.append(("top","backend", self.backend_cb.currentText()))
            if not self.cfg.set_existing_top("vsync", "true" if self.vsync_cb.isChecked() else "false"):
                missing.append(("top","vsync", "true" if self.vsync_cb.isChecked() else "false"))
            if not self.cfg.set_existing_top("inactive-opacity", str(self.inactive.value())):
                missing.append(("top","inactive-opacity", str(self.inactive.value())))
            if not self.cfg.set_existing_top("active-opacity", str(self.active.value())):
                missing.append(("top","active-opacity", str(self.active.value())))
            if not self.cfg.set_existing_block_key("blur","method", self.blur_method.currentText()):
                missing.append(("block","blur","method", self.blur_method.currentText()))
            if not self.cfg.set_existing_block_key("blur","strength", str(int(self.blur_strength.value()))):
                missing.append(("block","blur","strength", str(int(self.blur_strength.value()))))
            if not self.cfg.set_existing_top("shadow", "true" if self.shadow_cb.isChecked() else "false"):
                missing.append(("top","shadow", "true" if self.shadow_cb.isChecked() else "false"))
            if not self.cfg.set_existing_top("shadow-opacity", str(self.shadow_op.value())):
                missing.append(("top","shadow-opacity", str(self.shadow_op.value())))
            if not self.cfg.set_existing_top("corner-radius", str(int(self.corner.value()))):
                missing.append(("top","corner-radius", str(int(self.corner.value()))))
            if not self.cfg.set_existing_top("fading", "true" if self.fading_cb.isChecked() else "false"):
                missing.append(("top","fading","true" if self.fading_cb.isChecked() else "false"))
            if not self.cfg.set_existing_top("fade-in-step", str(self.fade_in.value())):
                missing.append(("top","fade-in-step", str(self.fade_in.value())))

            # If nothing missing just save
            if not missing:
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved {self.cfg.path}")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return

            # Ask user whether to append missing keys/blocks
            msg = "Some keys were not found in your picom.conf. By default the editor only edits existing keys.\n\nMissing items:\n"
            for m in missing:
                if m[0] == "top":
                    msg += f" - {m[1]} = {m[2]}\n"
                else:
                    msg += f" - {m[1]}.{m[2]} = {m[3]}\n"
            msg += "\nAppend missing keys/blocks? (No = save only existing changes)"
            resp = QMessageBox.question(self, "Missing keys", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if resp == QMessageBox.StandardButton.Cancel:
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved existing-key changes to {self.cfg.path}")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return
            if resp == QMessageBox.StandardButton.No:
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved existing-key changes to {self.cfg.path}")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return
            # Yes -> append missing keys / create blocks as needed
            for m in missing:
                if m[0] == "top":
                    self.cfg.append_top_key(m[1], m[2])
                else:
                    h, bo, bc = self.cfg._find_block(m[1])
                    if bo is None:
                        self.cfg.append_block(m[1], {m[2]: m[3]})
                    else:
                        # insert before closing brace
                        self.cfg.lines.insert(bc, f"    {m[2]} = {m[3]};\n")
            try:
                self.cfg.save(backup=True)
                QMessageBox.information(self, "Saved", f"Saved (with appended items) to {self.cfg.path}")
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")

    return PicomEditor(core_config)
