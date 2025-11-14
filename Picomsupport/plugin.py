# plugin.py — Picom editor plugin (lazy-loaded)
# No Qt objects are created at import time. Use create_editor(core_config).

import os
from pathlib import Path
import re
from datetime import datetime
import shutil

PICOM_PATH_CANDIDATES = [
    os.path.expanduser("~/.config/picom.conf"),
    os.path.expanduser("~/.config/pipewire/picom.conf"),
    os.path.expanduser("~/.config/gtk-3.0/picom.conf"),
]

def find_picom_path() -> str:
    for p in PICOM_PATH_CANDIDATES:
        if os.path.isfile(p):
            return p
    # default to first candidate if none exist (will create on save)
    return PICOM_PATH_CANDIDATES[0]

# ---------- minimal safe Picom config helper that edits only changed lines ----------
class PicomConfig:
    """
    Lightweight editor for picom.conf that:
      - Loads lines preserving newline endings
      - Can get and set top-level key = value lines (e.g. vsync = true;)
      - Can parse and edit a 'blur: { ... };' block keys like method, strength
      - Saves with backup and writes only modified lines
    """
    def __init__(self, path: str = None):
        self.path = Path(path or find_picom_path())
        self.lines = []
        self.load()

    def load(self):
        if self.path.exists():
            self.lines = self.path.read_text(encoding="utf-8").splitlines(True)
        else:
            self.lines = []
        # normalize: ensure all lines end with newline
        self.lines = [ln if ln.endswith("\n") else ln + "\n" for ln in self.lines]

    def _find_top_key_idx(self, key: str):
        # match lines like: key = value;
        pattern = re.compile(r'^\s*' + re.escape(key) + r'\s*=')
        for i, ln in enumerate(self.lines):
            if pattern.match(ln):
                return i
        return None

    def _find_block(self, block_name: str):
        """
        Find block like:
        block_name:
        {
           ...;
        };
        Return (start_idx_of_block_header, start_brace_idx, end_brace_idx)
        or (None,None,None) if not found.
        """
        header_pattern = re.compile(r'^\s*' + re.escape(block_name) + r'\s*:\s*$')
        brace_open = None
        brace_close = None
        header_idx = None
        for i, ln in enumerate(self.lines):
            if header_pattern.match(ln):
                header_idx = i
                # next non-empty line should be '{'
                j = i + 1
                while j < len(self.lines) and self.lines[j].strip() == "":
                    j += 1
                if j < len(self.lines) and self.lines[j].strip().startswith("{"):
                    brace_open = j
                    # find matching closing brace on or after j
                    k = j + 1
                    depth = 1
                    while k < len(self.lines):
                        if "{" in self.lines[k]:
                            depth += self.lines[k].count("{")
                        if "}" in self.lines[k]:
                            depth -= self.lines[k].count("}")
                            if depth == 0:
                                brace_close = k
                                break
                        k += 1
                break
        return header_idx, brace_open, brace_close

    def get(self, key: str, default=None):
        # support block keys with dot: e.g. blur.strength
        if "." in key:
            block, sub = key.split(".", 1)
            h, bo, bc = self._find_block(block)
            if bo is None or bc is None:
                return default
            pat = re.compile(r'^\s*' + re.escape(sub) + r'\s*=\s*(.+);')
            for ln in self.lines[bo+1:bc]:
                m = pat.match(ln)
                if m:
                    val = m.group(1).strip()
                    # strip quotes if present
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        return val[1:-1]
                    return val
            return default
        else:
            idx = self._find_top_key_idx(key)
            if idx is None:
                return default
            ln = self.lines[idx]
            m = re.match(r'^\s*' + re.escape(key) + r'\s*=\s*(.+);', ln)
            if m:
                val = m.group(1).strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    return val[1:-1]
                return val
            return default

    def set(self, key: str, value):
        # convert booleans to 'true'/'false' strings if bool passed
        if isinstance(value, bool):
            vstr = "true" if value else "false"
        else:
            vstr = str(value)
        # add semicolon at end if not inside block
        if "." in key:
            block, sub = key.split(".", 1)
            h, bo, bc = self._find_block(block)
            if bo is None:
                # create a block at end
                insert_at = len(self.lines)
                self.lines.append(f"\n{block}:\n{{\n    {sub} = {vstr};\n}};\n")
                return
            # update existing subkey inside block, or insert before closing brace
            pat = re.compile(r'^\s*' + re.escape(sub) + r'\s*=')
            for i in range(bo+1, bc):
                if pat.match(self.lines[i]):
                    # keep indentation
                    indent = re.match(r'^(\s*)', self.lines[i]).group(1)
                    self.lines[i] = f"{indent}{sub} = {vstr};\n"
                    return
            # not found -> insert before bc
            indent = "    "
            self.lines.insert(bc, f"{indent}{sub} = {vstr};\n")
            return
        else:
            idx = self._find_top_key_idx(key)
            line = f"{key} = {vstr};\n"
            if idx is None:
                # append at end
                # ensure there's a blank line before appending for readability
                if len(self.lines) and not self.lines[-1].endswith("\n\n"):
                    self.lines.append("\n")
                self.lines.append(line)
            else:
                # replace line
                self.lines[idx] = line

    def save(self, backup: bool = True):
        if backup and self.path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = self.path.with_suffix(self.path.suffix + f".bak.{ts}")
            shutil.copy2(self.path, bak)
        # ensure parent exists
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(self.lines), encoding="utf-8")
        # reload to normalize
        self.load()

# ---------- factory that builds and returns the Qt widget (lazy) ----------
def create_editor(core_config=None):
    """
    Factory called by the core after QApplication exists.
    Returns a QWidget instance (Editor widget).
    """

    # Import Qt inside factory to avoid creating Qt objects at module import time
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
        def __init__(self, core_cfg=None):
            super().__init__()
            # always edit user's picom.conf (not core's i3 config)
            self.cfg_path = find_picom_path()
            self.cfg = PicomConfig(self.cfg_path)
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout()
            self.setLayout(layout)

            layout.addWidget(QLabel(f"Editing: {self.cfg.path}"))

            # Backend
            layout.addWidget(QLabel("Backend"))
            self.backend_cb = QComboBox()
            self.backend_cb.addItems(["xrender", "glx", "xr_glx_hybrid"])
            self.backend_cb.setCurrentText(self.cfg.get("backend", "glx"))
            layout.addWidget(self.backend_cb)

            # VSync
            self.vsync_cb = QCheckBox("VSync")
            self.vsync_cb.setChecked(str(self.cfg.get("vsync", "true")).lower() == "true")
            layout.addWidget(self.vsync_cb)

            # Opacities
            self.inactive_spin = QDoubleSpinBox()
            self.inactive_spin.setRange(0.0, 1.0); self.inactive_spin.setSingleStep(0.01)
            try:
                self.inactive_spin.setValue(float(self.cfg.get("inactive-opacity", 0.7)))
            except Exception:
                self.inactive_spin.setValue(0.7)
            layout.addWidget(QLabel("Inactive opacity"))
            layout.addWidget(self.inactive_spin)

            self.active_spin = QDoubleSpinBox()
            self.active_spin.setRange(0.0, 1.0); self.active_spin.setSingleStep(0.01)
            try:
                self.active_spin.setValue(float(self.cfg.get("active-opacity", 1.0)))
            except Exception:
                self.active_spin.setValue(1.0)
            layout.addWidget(QLabel("Active opacity"))
            layout.addWidget(self.active_spin)

            self.frame_spin = QDoubleSpinBox()
            self.frame_spin.setRange(0.0, 1.0); self.frame_spin.setSingleStep(0.01)
            try:
                self.frame_spin.setValue(float(self.cfg.get("frame-opacity", 1.0)))
            except Exception:
                self.frame_spin.setValue(1.0)
            layout.addWidget(QLabel("Frame opacity"))
            layout.addWidget(self.frame_spin)

            # Blur block
            layout.addWidget(QLabel("Blur method"))
            self.blur_method_cb = QComboBox()
            self.blur_method_cb.addItems(["none", "kawase", "dual_kawase", "box", "gaussian"])
            self.blur_method_cb.setCurrentText(self.cfg.get("blur.method", "dual_kawase") or "dual_kawase")
            layout.addWidget(self.blur_method_cb)

            layout.addWidget(QLabel("Blur strength"))
            self.blur_strength_spin = QDoubleSpinBox()
            self.blur_strength_spin.setRange(0, 50); self.blur_strength_spin.setSingleStep(1)
            try:
                self.blur_strength_spin.setValue(float(self.cfg.get("blur.strength", 5)))
            except Exception:
                self.blur_strength_spin.setValue(5)
            layout.addWidget(self.blur_strength_spin)

            # Shadows
            self.shadow_cb = QCheckBox("Enable shadow")
            self.shadow_cb.setChecked(str(self.cfg.get("shadow", "true")).lower() == "true")
            layout.addWidget(self.shadow_cb)

            self.shadow_radius_spin = QDoubleSpinBox()
            self.shadow_radius_spin.setRange(0, 200); self.shadow_radius_spin.setSingleStep(1)
            try:
                self.shadow_radius_spin.setValue(float(self.cfg.get("shadow-radius", 12)))
            except Exception:
                self.shadow_radius_spin.setValue(12)
            layout.addWidget(QLabel("Shadow radius"))
            layout.addWidget(self.shadow_radius_spin)

            self.shadow_opacity_spin = QDoubleSpinBox()
            self.shadow_opacity_spin.setRange(0.0, 1.0); self.shadow_opacity_spin.setSingleStep(0.01)
            try:
                self.shadow_opacity_spin.setValue(float(self.cfg.get("shadow-opacity", 0.25)))
            except Exception:
                self.shadow_opacity_spin.setValue(0.25)
            layout.addWidget(QLabel("Shadow opacity"))
            layout.addWidget(self.shadow_opacity_spin)

            # Rounded corners
            self.rounded_cb = QCheckBox("Enable rounded corners")
            self.rounded_cb.setChecked(str(self.cfg.get("rounded-corners", "true")).lower() == "true")
            layout.addWidget(self.rounded_cb)

            self.corner_spin = QDoubleSpinBox()
            self.corner_spin.setRange(0, 200); self.corner_spin.setSingleStep(1)
            try:
                self.corner_spin.setValue(int(float(self.cfg.get("corner-radius", 10))))
            except Exception:
                self.corner_spin.setValue(10)
            layout.addWidget(QLabel("Corner radius"))
            layout.addWidget(self.corner_spin)

            # Fading
            self.fading_cb = QCheckBox("Enable fading")
            self.fading_cb.setChecked(str(self.cfg.get("fading", "true")).lower() == "true")
            layout.addWidget(self.fading_cb)

            self.fade_in_spin = QDoubleSpinBox()
            self.fade_in_spin.setRange(0.0, 1.0); self.fade_in_spin.setSingleStep(0.01)
            try:
                self.fade_in_spin.setValue(float(self.cfg.get("fade-in-step", 0.03)))
            except Exception:
                self.fade_in_spin.setValue(0.03)
            layout.addWidget(QLabel("Fade-in step"))
            layout.addWidget(self.fade_in_spin)

            self.fade_out_spin = QDoubleSpinBox()
            self.fade_out_spin.setRange(0.0, 1.0); self.fade_out_spin.setSingleStep(0.01)
            try:
                self.fade_out_spin.setValue(float(self.cfg.get("fade-out-step", 0.03)))
            except Exception:
                self.fade_out_spin.setValue(0.03)
            layout.addWidget(QLabel("Fade-out step"))
            layout.addWidget(self.fade_out_spin)

            self.fade_delta_spin = QDoubleSpinBox()
            self.fade_delta_spin.setRange(0, 1000); self.fade_delta_spin.setSingleStep(1)
            try:
                self.fade_delta_spin.setValue(int(float(self.cfg.get("fade-delta", 10))))
            except Exception:
                self.fade_delta_spin.setValue(10)
            layout.addWidget(QLabel("Fade delta (ms)"))
            layout.addWidget(self.fade_delta_spin)

            # Save button row
            btn_row = QHBoxLayout()
            save_btn = QPushButton("Save Picom config")
            save_btn.clicked.connect(self._on_save)
            btn_row.addWidget(save_btn)
            layout.addLayout(btn_row)

        def _on_save(self):
            # set values back into cfg
            self.cfg.set("backend", self.backend_cb.currentText())
            self.cfg.set("vsync", "true" if self.vsync_cb.isChecked() else "false")
            self.cfg.set("inactive-opacity", str(self.inactive_spin.value()))
            self.cfg.set("active-opacity", str(self.active_spin.value()))
            self.cfg.set("frame-opacity", str(self.frame_spin.value()))
            self.cfg.set("blur.method", self.blur_method_cb.currentText())
            self.cfg.set("blur.strength", str(int(self.blur_strength_spin.value())))
            self.cfg.set("shadow", "true" if self.shadow_cb.isChecked() else "false")
            self.cfg.set("shadow-radius", str(int(self.shadow_radius_spin.value())))
            self.cfg.set("shadow-opacity", str(self.shadow_opacity_spin.value()))
            self.cfg.set("rounded-corners", "true" if self.rounded_cb.isChecked() else "false")
            self.cfg.set("corner-radius", str(int(self.corner_spin.value())))
            self.cfg.set("fading", "true" if self.fading_cb.isChecked() else "false")
            self.cfg.set("fade-in-step", str(self.fade_in_spin.value()))
            self.cfg.set("fade-out-step", str(self.fade_out_spin.value()))
            self.cfg.set("fade-delta", str(int(self.fade_delta_spin.value())))
            try:
                self.cfg.save(backup=True)
                QMessageBox.information(self, "Saved", f"Saved {self.cfg.path}")
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")

    # return an instance of the editor (core will call this after QApplication exists)
    return PicomEditor(core_config)

