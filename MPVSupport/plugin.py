# plugin.py — mpv config editor plugin (safe, preserves formatting)
import os
import re
import shutil
from pathlib import Path
from datetime import datetime

MPV_PATH_CANDIDATES = [
    os.path.expanduser("~/.config/mpv/mpv.conf"),
    os.path.expanduser("~/.mpv/config"),
]

def find_mpv_path():
    for p in MPV_PATH_CANDIDATES:
        if os.path.isfile(p):
            return p
    # default to user config path
    return MPV_PATH_CANDIDATES[0]

class MPVConfig:
    """
    Simple mpv.conf editor:
      - preserves file layout, comments and whitespace
      - get(key), set_existing(key, value) -> bool (replace only if key found)
      - append_key(key, value) -> True (adds key=value at EOF)
      - save(backup=True)
    Notes:
      - mpv supports flags (presence of a key) and key=value forms. This editor
        will always write key=value when setting; reading will handle both forms.
    """
    # Matches a line that starts with the key, optionally followed by =value, and optional trailing comment.
    KEY_RE_TEMPLATE = r'^(\s*{key}\s*)(?:=\s*(.*?))?(\s*(?:#.*)?)$'

    def __init__(self, path=None):
        self.path = Path(path or find_mpv_path())
        self.lines = []
        self.load()

    def load(self):
        if self.path.exists():
            raw = self.path.read_text(encoding="utf-8", errors="surrogateescape")
            self.lines = raw.splitlines(True)
        else:
            self.lines = ["\n"]
        # normalize newline ending
        self.lines = [ln if ln.endswith("\n") else ln + "\n" for ln in self.lines]

    def _find_key_idx(self, key: str):
        """
        Return index of first line that contains key (as standalone token or key=value).
        Case-insensitive search for friendliness (mpv keys are usually lowercase).
        """
        pat = re.compile(self.KEY_RE_TEMPLATE.format(key=re.escape(key)), re.IGNORECASE)
        for i, ln in enumerate(self.lines):
            if pat.match(ln):
                return i
        return None

    def get(self, key: str, default=None):
        """
        Return raw value for key (str) with surrounding quotes stripped. If line exists without value (flag),
        return "true". If not found, return default.
        """
        idx = self._find_key_idx(key)
        if idx is None:
            return default
        pat = re.compile(self.KEY_RE_TEMPLATE.format(key=re.escape(key)), re.IGNORECASE)
        m = pat.match(self.lines[idx])
        if not m:
            return default
        val = m.group(2)
        if val is None:
            # flag present (no explicit value) -> treat as "true"
            return "true"
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            return val[1:-1]
        return val

    def _format_value(self, v):
        # keep booleans as true/false, numbers bare, quoted strings preserved, otherwise bare string
        if isinstance(v, bool):
            return "yes" if v else "no"  # mpv recognizes yes/no; many configs use yes/no
        s = str(v).strip()
        if s.lower() in ("yes", "no", "true", "false"):
            # normalize to yes/no
            if s.lower() in ("true", "yes"):
                return "yes"
            return "no"
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
        # keep quoted
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s
        # mpv usually accepts unquoted strings; we will leave them unquoted
        return s

    def set_existing(self, key: str, value) -> bool:
        """
        Replace the first existing occurrence of key's value token only.
        Returns True if replaced, False if not found.
        """
        idx = self._find_key_idx(key)
        if idx is None:
            return False
        pat = re.compile(self.KEY_RE_TEMPLATE.format(key=re.escape(key)))
        ln = self.lines[idx]
        m = pat.match(ln)
        if not m:
            # fallback: overwrite the line entirely
            val_text = self._format_value(value)
            self.lines[idx] = f"{key}={val_text}\n"
            return True
        left = m.group(1)  # leading key + whitespace
        trailing = m.group(3) or ""
        if trailing and not trailing.endswith("\n"):
            trailing = trailing + "\n"
        val_text = self._format_value(value)
        # ensure there is exactly one '=' between key and value (no extra spaces needed)
        self.lines[idx] = f"{left}={val_text}{trailing}"
        return True

    def append_key(self, key: str, value):
        """
        Append key=value to end of file (ensuring a blank line separation).
        """
        val_text = self._format_value(value)
        if not self.lines or not self.lines[-1].endswith("\n"):
            self.lines.append("\n")
        # ensure blank line before new keys
        if len(self.lines) >= 1 and self.lines[-1].strip() != "":
            self.lines.append("\n")
        self.lines.append(f"{key}={val_text}\n")
        return True

    def save(self, backup: bool = True):
        if backup and self.path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = self.path.with_suffix(self.path.suffix + f".bak.{ts}")
            try:
                shutil.copy2(self.path, bak)
            except Exception:
                pass
        # ensure parent exists
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8", errors="surrogateescape") as f:
                f.writelines(self.lines)
        except Exception:
            raise

# Lazy UI factory
def create_editor(core_config=None):
    try:
        from PyQt6.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QComboBox, QCheckBox,
            QSpinBox, QPushButton, QMessageBox, QHBoxLayout, QGroupBox, QFormLayout
        )
        from PyQt6.QtCore import Qt
    except Exception:
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QComboBox, QCheckBox,
            QSpinBox, QPushButton, QMessageBox, QHBoxLayout, QGroupBox, QFormLayout
        )
        from PyQt5.QtCore import Qt

    class MPVEditor(QWidget):
        def __init__(self, *_):
            super().__init__()
            self.cfg = MPVConfig(find_mpv_path())
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout()
            self.setLayout(layout)
            layout.addWidget(QLabel(f"Editing: {self.cfg.path}"))

            # Playback group
            play_g = QGroupBox("Playback")
            play_form = QFormLayout()
            play_g.setLayout(play_form)

            # hardware decoding
            self.hwdec_cb = QComboBox()
            hw_opts = ["no", "auto", "vaapi", "vdpau", "dxva2", "nvdec"]
            self.hwdec_cb.addItems(hw_opts)
            cur_hw = self.cfg.get("hwdec", "")
            if cur_hw:
                cur_hw_clean = cur_hw.strip().lower().strip('"').strip("'")
                if cur_hw_clean in hw_opts:
                    self.hwdec_cb.setCurrentText(cur_hw_clean)
            play_form.addRow(QLabel("hwdec"), self.hwdec_cb)

            # video output (vo)
            self.vo_cb = QComboBox()
            vo_opts = ["gpu", "x11", "opengl", "wayland"]
            self.vo_cb.addItems(vo_opts)
            cur_vo = self.cfg.get("vo", "")
            if cur_vo:
                cur_vo_clean = cur_vo.strip().lower().strip('"').strip("'")
                if cur_vo_clean in vo_opts:
                    self.vo_cb.setCurrentText(cur_vo_clean)
            play_form.addRow(QLabel("vo"), self.vo_cb)

            # volume
            self.vol_spin = QSpinBox(); self.vol_spin.setRange(0, 1000)
            try:
                cur_vol = self.cfg.get("volume", None)
                if cur_vol is not None:
                    self.vol_spin.setValue(int(float(cur_vol)))
                else:
                    self.vol_spin.setValue(100)
            except Exception:
                self.vol_spin.setValue(100)
            play_form.addRow(QLabel("volume (default)"), self.vol_spin)

            layout.addWidget(play_g)

            # Display group
            disp_g = QGroupBox("Display")
            disp_form = QFormLayout()
            disp_g.setLayout(disp_form)

            self.fullscreen_cb = QCheckBox("fullscreen")
            cur_full = self.cfg.get("fullscreen", None)
            if cur_full is not None:
                self.fullscreen_cb.setChecked(str(cur_full).strip().lower() in ("yes", "true", "1"))
            disp_form.addRow(self.fullscreen_cb)

            selfhw_cb_label = QLabel("border")  # mpv uses border=no to hide border in some setups
            self.border_cb = QCheckBox("show border (border=yes/no)")
            cur_border = self.cfg.get("border", None)
            if cur_border is not None:
                self.border_cb.setChecked(str(cur_border).strip().lower() in ("yes", "true", "1"))
            disp_form.addRow(self.border_cb)

            layout.addWidget(disp_g)

            # Other options
            other_g = QGroupBox("Other")
            other_form = QFormLayout()
            other_g.setLayout(other_form)

            self.loop_cb = QCheckBox("loop (loop-playlist or loop-file behavior may vary)")
            cur_loop = self.cfg.get("loop", None)
            if cur_loop is not None:
                self.loop_cb.setChecked(str(cur_loop).strip().lower() in ("yes", "true", "inf", "1"))
            other_form.addRow(self.loop_cb)

            layout.addWidget(other_g)

            # Save button row
            row = QHBoxLayout()
            save_btn = QPushButton("Save (safe)")
            save_btn.clicked.connect(self._on_save)
            row.addWidget(save_btn)
            layout.addLayout(row)

        def _on_save(self):
            missing = []
            # try to set existing keys
            if not self.cfg.set_existing("hwdec", self.hwdec_cb.currentText()):
                missing.append(("hwdec", self.hwdec_cb.currentText()))
            if not self.cfg.set_existing("vo", self.vo_cb.currentText()):
                missing.append(("vo", self.vo_cb.currentText()))
            if not self.cfg.set_existing("volume", str(self.vol_spin.value())):
                missing.append(("volume", str(self.vol_spin.value())))
            # fullscreen -> write yes/no
            fs_val = "yes" if self.fullscreen_cb.isChecked() else "no"
            if not self.cfg.set_existing("fullscreen", fs_val):
                missing.append(("fullscreen", fs_val))
            border_val = "yes" if self.border_cb.isChecked() else "no"
            if not self.cfg.set_existing("border", border_val):
                missing.append(("border", border_val))
            loop_val = "yes" if self.loop_cb.isChecked() else "no"
            if not self.cfg.set_existing("loop", loop_val):
                missing.append(("loop", loop_val))

            # If nothing missing, save
            if not missing:
                try:
                    self.cfg.save(backup=True)
                    QMessageBox.information(self, "Saved", f"Saved {self.cfg.path}")
                except PermissionError:
                    QMessageBox.critical(self, "Permission denied",
                        f"Failed to save {self.cfg.path}. You may need elevated privileges for system files.")
                except Exception as e:
                    QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")
                return

            # ask user whether to append missing keys
            msg = "Some mpv options were not found in your mpv.conf. By default the editor only edits existing keys.\n\nMissing items:\n"
            for k, v in missing:
                msg += f" - {k} = {v}\n"
            msg += "\nAppend missing keys? (No = save only existing changes)"
            resp = QMessageBox.question(self, "Missing keys", msg,
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if resp == QMessageBox.StandardButton.Cancel:
                # treat as save existing changes
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

            # Yes -> append missing keys
            for k, v in missing:
                self.cfg.append_key(k, v)
            try:
                self.cfg.save(backup=True)
                QMessageBox.information(self, "Saved", f"Saved (with appended items) to {self.cfg.path}")
            except Exception as e:
                QMessageBox.critical(self, "Save failed", f"Failed to save: {e}")

    return MPVEditor(core_config)
