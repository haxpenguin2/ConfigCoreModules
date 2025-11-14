# plugin.py — Picom editor plugin (safe, conservative edits only)
# Lazy-load GUI; only modifies existing keys by default; prompts before appending.

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
    Minimal parser that preserves formatting and only edits existing value tokens by default.
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

    # find top-level key line index (key = ...;)
    def _find_top_key_idx(self, key):
        pat = re.compile(r'^\s*' + re.escape(key) + r'\s*=')
        for i, ln in enumerate(self.lines):
            if pat.match(ln):
                return i
        return None

    # find block (header line like 'blur:' then { ... } ;) returning (header_idx, open_idx, close_idx)
    def _find_block(self, block_name):
        header_pat = re.compile(r'^\s*' + re.escape(block_name) + r'\s*:\s*$')
        header_idx = None
        open_idx = None
        close_idx = None
        for i, ln in enumerate(self.lines):
            if header_pat.match(ln):
                header_idx = i
                # find next '{'
                j = i + 1
                while j < len(self.lines) and self.lines[j].strip() == "":
                    j += 1
                if j < len(self.lines) and self.lines[j].strip().startswith("{"):
                    open_idx = j
                    depth = 1
                    k = j + 1
                    while k < len(self.lines):
                        if "{" in self.lines[k]:
                            depth += self.lines[k].count("{")
                        if "}" in self.lines[k]:
                            depth -= self.lines[k].count("}")
                            if depth == 0:
                                close_idx = k
                                break
                        k += 1
                break
        return header_idx, open_idx, close_idx

    # read a key; supports block.key
    def get(self, key, default=None):
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

    # ONLY change existing top-level key. Returns True if changed, False if key not found.
    def set_existing_top(self, key, value):
        idx = self._find_top_key_idx(key)
        if idx is None:
            return False
        # keep left-side spacing and replace value token, preserve semicolon/newline
        ln = self.lines[idx]
        # find start of assignment after '='
        prefix_match = re.match(r'^(\s*' + re.escape(key) + r'\s*=\s*)(.*?)(;?\s*\n?)$', ln)
        if not prefix_match:
            # fallback - just replace whole line
            self.lines[idx] = f"{key} = {value};\n"
            return True
        prefix = prefix_match.group(1)
        suffix = prefix_match.group(3)
        self.lines[idx] = f"{prefix}{value}{suffix if suffix.endswith('\\n') else suffix+'\\n'}"
        return True

    # ONLY change existing sub-key inside an existing block. Returns True if changed, False if not present.
    def set_existing_block_key(self, block, sub, value):
        h, bo, bc = self._find_block(block)
        if bo is None or bc is None:
            return False
        sub_pat = re.compile(r'^\s*' + re.escape(sub) + r'\s*=')
        for i in range(bo+1, bc):
            if sub_pat.match(self.lines[i]):
                # keep indentation
                indent = re.match(r'^(\s*)', self.lines[i]).group(1)
                self.lines[i] = f"{indent}{sub} = {value};\n"
                return True
        return False

    # Append top-level key (used only when user confirms) — returns True
    def append_top_key(self, key, value):
        # append at end, preserving a blank line
        if len(self.lines) and not self.lines[-1].endswith("\n\n"):
            self.lines.append("\n")
        self.lines.append(f"{key} = {value};\n")
        return True

    # Append a block (used only when user confirms) — returns True
    def append_block(self, block, pairs: dict):
        if len(self.lines) and not self.lines[-1].endswith("\n\n"):
            self.lines.append("\n")
        self.lines.append(f"{block}:\n{{\n")
        for k, v in pairs.items():
            self.lines.append(f"    {k} = {v};\n")
        self.lines.append("};\n")
        return True

    # Save absolute: creates timestamped backup if requested
    def save(self, backup=True):
        if backup and self.path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = self.path.with_suffix(self.path.suffix + f".bak.{ts}")
            shutil.copy2(self.path, bak)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(self.lines), encoding="utf-8")
        self.load()

# Lazy GUI factory (import Qt only inside factory)
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
            self.backend_cb = QComboBox(); self.backend_cb.addItems(["xrender", "glx", "xr_glx_hybrid"])
            self.backend_cb.setCurrentText(self.cfg.get("backend", "glx") or "glx")
            layout.addWidget(self.backend_cb)

            # vsync
            self.vsync_cb = QCheckBox("VSync"); self.vsync_cb.setChecked(str(self.cfg.get("vsync", "true")).lower()=="true"); layout.addWidget(self.vsync_cb)

            # opacities (top-level)
            layout.addWidget(QLabel("Inactive opacity"))
            self.inactive = QDoubleSpinBox(); self.inactive.setRange(0.0, 1.0); self.inactive.setSingleStep(0.01)
            try: self.inactive.setValue(float(self.cfg.get("inactive-opacity", 0.7)))
            except: self.inactive.setValue(0.7)
            layout.addWidget(self.inactive)

            layout.addWidget(QLabel("Active opacity"))
            self.active = QDoubleSpinBox(); self.active.setRange(0.0, 1.0); self.active.setSingleStep(0.01)
            try: self.active.setValue(float(self.cfg.get("active-opacity", 1.0)))
            except: self.active.setValue(1.0)
            layout.addWidget(self.active)

            # blur block keys (show UI but edits will only modify existing block keys by default)
            layout.addWidget(QLabel("Blur method (block)"))
            self.blur_method = QComboBox(); self.blur_method.addItems(["dual_kawase","kawase","box","gaussian","none"])
            bm = self.cfg.get("blur.method", "")
            if bm: self.blur_method.setCurrentText(bm)
            layout.addWidget(self.blur_method)

            layout.addWidget(QLabel("Blur strength (block)"))
            self.blur_strength = QDoubleSpinBox(); self.blur_strength.setRange(0,100); self.blur_strength.setSingleStep(1)
            try: self.blur_strength.setValue(float(self.cfg.get("blur.strength", 5)))
            except: self.blur_strength.setValue(5)
            layout.addWidget(self.blur_strength)

            # shadows
            self.shadow_cb = QCheckBox("Shadow"); self.shadow_cb.setChecked(str(self.cfg.get("shadow", "true")).lower()=="true"); layout.addWidget(self.shadow_cb)
            layout.addWidget(QLabel("Shadow opacity"))
            self.shadow_op = QDoubleSpinBox(); self.shadow_op.setRange(0.0,1.0); self.shadow_op.setSingleStep(0.01)
            try: self.shadow_op.setValue(float(self.cfg.get("shadow-opacity", 0.25)))
            except: self.shadow_op.setValue(0.25)
            layout.addWidget(self.shadow_op)

            # corner radius
            layout.addWidget(QLabel("Corner radius"))
            self.corner = QDoubleSpinBox(); self.corner.setRange(0,200); self.corner.setSingleStep(1)
            try: self.corner.setValue(int(float(self.cfg.get("corner-radius", 10))))
            except: self.corner.setValue(10)
            layout.addWidget(self.corner)

            # fading
            self.fading_cb = QCheckBox("Fading"); self.fading_cb.setChecked(str(self.cfg.get("fading","true")).lower()=="true"); layout.addWidget(self.fading_cb)
            layout.addWidget(QLabel("Fade-in step"))
            self.fade_in = QDoubleSpinBox(); self.fade_in.setRange(0.0,1.0); self.fade_in.setSingleStep(0.01)
            try: self.fade_in.setValue(float(self.cfg.get("fade-in-step", 0.03)))
            except: self.fade_in.setValue(0.03)
            layout.addWidget(self.fade_in)

            # Save
            btn_row = QHBoxLayout()
            save_btn = QPushButton("Save (safe)")
            save_btn.clicked.connect(self._on_save)
            btn_row.addWidget(save_btn)
            layout.addLayout(btn_row)

        def _on_save(self):
            # Attempt to set existing keys first
            missing_actions = []  # list of tuples describing missing targets: ("top", key, value) or ("block", block, sub, value)
            changed = []
            # top-level keys:
            if not self.cfg.set_existing_top("backend", self.backend_cb.currentText()):
                missing_actions.append(("top", "backend", self.backend_cb.currentText()))
            if not self.cfg.set_existing_top("vsync", "true" if self.vsync_cb.isChecked() else "false"):
                missing_actions.append(("top","vsync","true" if self.vsync_cb.isChecked() else "false"))
            if not self.cfg.set_existing_top("inactive-opacity", str(self.inactive.value())):
                missing_actions.append(("top","inactive-opacity", str(self.inactive.value())))
            if not self.cfg.set_existing_top("active-opacity", str(self.active.value())):
                missing_actions.append(("top","active-opacity", str(self.active.value())))
            if not self.cfg.set_existing_block_key("blur","method", f'"{self.blur_method.currentText()}"'):
                missing_actions.append(("block","blur","method", f'"{self.blur_method.currentText()}"'))
            if not self.cfg.set_existing_block_key("blur","strength", str(int(self.blur_strength.value()))):
                missing_actions.append(("block","blur","strength", str(int(self.blur_strength.value()))))
            if not self.cfg.set_existing_top("shadow", "true" if self.shadow_cb.isChecked() else "false"):
                missing_actions.append(("top","shadow","true" if self.shadow_cb.isChecked() else "false"))
            if not self.cfg.set_existing_top("shadow-opacity", str(self.shadow_op.value())):
                missing_actions.append(("top","shadow-opacity", str(self.shadow_op.value())))
            if not self.cfg.set_existing_top("corner-radius", str(int(self.corner.value()))):
                missing_actions.append(("top","corner-radius", str(int(self.corner.value()))))
            if not self.cfg.set_existing_top("fading", "true" if self.fading_cb.isChecked() else "false"):
                missing_actions.append(("top","fading","true" if self.fading_cb.isChecked() else "false"))
            if not self.cfg.set_existing_top("fade-in-step", str(self.fade_in.value())):
                missing_actions.append(("top","fade-in-step", str(self.fade_in.value())))

            # if nothing missing, write immediately
            if not missing_actions:
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved {self.cfg.path}")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return

            # Otherwise ask user what to do: show a list and ask whether to append missing items (only if user agrees)
            msg = "Some keys you changed were NOT found in your existing picom.conf. By default the editor does not create new blocks or keys to avoid changing structure.\n\nMissing items:\n"
            for ma in missing_actions:
                if ma[0] == "top":
                    msg += f"  (top) {ma[1]} = {ma[2]}\n"
                else:
                    msg += f"  (block) {ma[1]}.{ma[2]} = {ma[3]}\n"
            msg += "\nDo you want the editor to append the missing TOP-LEVEL keys and blocks? (Cancel will save only the existing-key changes.)"
            resp = QMessageBox.question(self, "Missing keys", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if resp == QMessageBox.StandardButton.Cancel:
                # save what we did (only existing changes) and return
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved existing-key changes to {self.cfg.path}")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return
            if resp == QMessageBox.StandardButton.No:
                # do not append missing, just save existing-key edits
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved existing-key changes to {self.cfg.path}")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return
            if resp == QMessageBox.StandardButton.Yes:
                # append missing top-level and blocks (top-level appended as key=value;) and blocks created for missing block keys
                for ma in missing_actions:
                    if ma[0] == "top":
                        self.cfg.append_top_key(ma[1], ma[2])
                    else:
                        # collect block-created pairs if block doesn't exist; if block exists but key missing, set_existing_block_key would have succeeded already
                        h, bo, bc = self.cfg._find_block(ma[1])
                        if bo is None:
                            # create block with this one pair
                            self.cfg.append_block(ma[1], {ma[2]: ma[3]})
                        else:
                            # block exists but key didn't — insert before closing brace
                            self.cfg.lines.insert(bc, f"    {ma[2]} = {ma[3]};\n")
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved (with appended missing items) to {self.cfg.path}")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")

    return PicomEditor(core_config)
