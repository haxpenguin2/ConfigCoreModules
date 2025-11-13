#!/usr/bin/env python3
"""
Picom Config Editor Plugin for ConfigCore
"""

import os
import re
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QCheckBox, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt

# Ensure we can import the core ConfigFile
try:
    from config_core import ConfigFile
except ImportError:
    # fallback if plugin is loaded standalone
    from ..config_core import ConfigFile

class EditorWidget(QWidget):
    def __init__(self, config: ConfigFile = None):
        super().__init__()
        self.cf_path = os.path.expanduser("~/.config/picom.conf")
        self.cf = None
        self.settings = {
            "backend": "glx",
            "vsync": True,
            "corner-radius": 0,
            "inactive-opacity": 0.7,
            "active-opacity": 1.0,
            "frame-opacity": 1.0,
            "fade-in-step": 0.03,
            "fade-out-step": 0.03,
            "fade-delta": 10,
            "fading": True,
            "blur-method": "dual_kawase",
            "blur-strength": 5,
            "shadow": True,
            "shadow-radius": 12,
            "shadow-opacity": 0.25,
        }

        self.load_config()
        self.build_ui()

    def load_config(self):
        if os.path.isfile(self.cf_path):
            try:
                self.cf = ConfigFile(self.cf_path)
                for line in self.cf.lines:
                    s = line.strip()
                    if s.startswith("#") or not s:
                        continue
                    # blur block
                    if "blur" in s or s.startswith("{") or s.startswith("}"):
                        continue
                    m = re.match(r'([\w-]+)\s*=\s*(.*);', s)
                    if m:
                        key = m.group(1).strip()
                        val = m.group(2).strip().strip('"')
                        if key in self.settings:
                            if val.lower() in ("true", "false"):
                                self.settings[key] = val.lower() == "true"
                            else:
                                try:
                                    self.settings[key] = float(val)
                                except:
                                    self.settings[key] = val
            except Exception as e:
                print("Failed to load picom config:", e)

    def build_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Backend selector
        backend_layout = QHBoxLayout()
        backend_layout.addWidget(QLabel("Backend:"))
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["glx", "xrender"])
        self.backend_combo.setCurrentText(self.settings["backend"])
        backend_layout.addWidget(self.backend_combo)
        layout.addLayout(backend_layout)

        # Vsync checkbox
        self.vsync_cb = QCheckBox("Vsync")
        self.vsync_cb.setChecked(self.settings["vsync"])
        layout.addWidget(self.vsync_cb)

        # Corner radius
        layout.addLayout(self._make_slider("Corner radius", "corner-radius", 0, 50))

        # Opacity
        layout.addLayout(self._make_slider("Inactive opacity", "inactive-opacity", 0, 100, True))
        layout.addLayout(self._make_slider("Active opacity", "active-opacity", 0, 100, True))
        layout.addLayout(self._make_slider("Frame opacity", "frame-opacity", 0, 100, True))

        # Fade settings
        layout.addLayout(self._make_slider("Fade in step", "fade-in-step", 1, 100, True, scale=0.01))
        layout.addLayout(self._make_slider("Fade out step", "fade-out-step", 1, 100, True, scale=0.01))
        layout.addLayout(self._make_slider("Fade delta (ms)", "fade-delta", 1, 50))
        self.fading_cb = QCheckBox("Enable fading")
        self.fading_cb.setChecked(self.settings["fading"])
        layout.addWidget(self.fading_cb)

        # Blur method
        blur_layout = QHBoxLayout()
        blur_layout.addWidget(QLabel("Blur method:"))
        self.blur_method_combo = QComboBox()
        self.blur_method_combo.addItems(["none", "kawase", "dual_kawase", "box", "gaussian"])
        self.blur_method_combo.setCurrentText(self.settings["blur-method"])
        blur_layout.addWidget(self.blur_method_combo)
        layout.addLayout(blur_layout)

        # Blur strength
        layout.addLayout(self._make_slider("Blur strength", "blur-strength", 0, 50))

        # Shadows
        self.shadow_cb = QCheckBox("Enable shadows")
        self.shadow_cb.setChecked(self.settings["shadow"])
        layout.addWidget(self.shadow_cb)
        layout.addLayout(self._make_slider("Shadow radius", "shadow-radius", 0, 50))
        layout.addLayout(self._make_slider("Shadow opacity", "shadow-opacity", 0, 100, True))

        # Save button
        save_btn = QPushButton("Save Picom Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)

        layout.addStretch()

    def _make_slider(self, label, key, minv, maxv, is_float=False, scale=1.0):
        lay = QHBoxLayout()
        lay.addWidget(QLabel(label))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(minv)
        slider.setMaximum(maxv)
        val = self.settings[key]
        if is_float:
            slider.setValue(int(val / scale))
        else:
            slider.setValue(int(val))
        lbl = QLabel(str(val))
        slider.valueChanged.connect(lambda v, k=key, l=lbl: self._slider_changed(v, k, l, is_float, scale))
        lay.addWidget(slider)
        lay.addWidget(lbl)
        return lay

    def _slider_changed(self, value, key, label, is_float, scale):
        if is_float:
            val = value * scale
            self.settings[key] = val
            label.setText(f"{val:.2f}")
        else:
            self.settings[key] = value
            label.setText(str(value))

    def save_config(self):
        if not self.cf:
            # Create a new file if it doesn't exist
            try:
                Path(self.cf_path).parent.mkdir(parents=True, exist_ok=True)
                Path(self.cf_path).touch()
                self.cf = ConfigFile(self.cf_path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Cannot create config file: {e}")
                return

        new_lines = []
        new_lines.append(f'backend = "{self.backend_combo.currentText()}";')
        new_lines.append(f'vsync = {"true" if self.vsync_cb.isChecked() else "false"};')
        new_lines.append(f'corner-radius = {self.settings["corner-radius"]};')
        new_lines.append(f'inactive-opacity = {self.settings["inactive-opacity"]:.2f};')
        new_lines.append(f'active-opacity = {self.settings["active-opacity"]:.2f};')
        new_lines.append(f'frame-opacity = {self.settings["frame-opacity"]:.2f};')
        new_lines.append(f'fade-in-step = {self.settings["fade-in-step"]:.2f};')
        new_lines.append(f'fade-out-step = {self.settings["fade-out-step"]:.2f};')
        new_lines.append(f'fade-delta = {self.settings["fade-delta"]};')
        new_lines.append(f'fading = {"true" if self.fading_cb.isChecked() else "false"};')
        new_lines.append("blur:")
        new_lines.append("{")
        new_lines.append(f'    method = "{self.blur_method_combo.currentText()}";')
        new_lines.append(f'    strength = {self.settings["blur-strength"]};')
        new_lines.append("};")
        new_lines.append(f'shadow = {"true" if self.shadow_cb.isChecked() else "false"};')
        new_lines.append(f'shadow-radius = {self.settings["shadow-radius"]};')
        new_lines.append(f'shadow-opacity = {self.settings["shadow-opacity"]:.2f};')

        try:
            self.cf.lines = new_lines
            backup_path = self.cf.save(backup=True)
            QMessageBox.information(self, "Saved", f"Picom config saved!\nBackup: {backup_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save Picom config: {e}")
