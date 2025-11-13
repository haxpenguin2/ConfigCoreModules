#!/usr/bin/env python3
"""
Picom Editor plugin for ConfigCore
Parses real Picom config syntax and populates sliders/checkboxes correctly.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSlider, QHBoxLayout, QPushButton, QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt
from pathlib import Path
import re

class EditorWidget(QWidget):
    def __init__(self, config=None):
        super().__init__()

        # Load ConfigFile from core, or default to picom.conf
        if config:
            self.cf = config
        else:
            from config_core import ConfigFile
            picom_path = Path.home() / ".config/picom.conf"
            self.cf = ConfigFile(str(picom_path)) if picom_path.exists() else None

        # Settings to display/edit: name -> type
        self.settings_defs = {
            "corner-radius": "int",
            "inactive-opacity": "float",
            "active-opacity": "float",
            "frame-opacity": "float",
            "fade-in-step": "float",
            "fade-out-step": "float",
            "fade-delta": "int",
            "fading": "bool",
            "shadow": "bool",
            "shadow-radius": "int",
            "shadow-opacity": "float",
            "blur-method": "str",
            "blur-strength": "int"
        }

        # Load current values
        self.settings = self._parse_config()

        self.setStyleSheet("""
            QWidget { background: #071018; color: #dbe7f5; font-family: 'Segoe UI', Roboto, sans-serif; }
            QLabel { font-size: 12pt; }
            QSlider::handle:horizontal { background: #5c5cff; border-radius: 8px; width: 16px; }
            QSlider::groove:horizontal { height: 10px; background: #444; border-radius: 5px; }
            QPushButton { background-color: #5c5cff; border-radius: 5px; padding: 5px; color: #e6eef8; }
            QPushButton:hover { background-color: #4545ff; }
            QCheckBox { padding: 2px; }
        """)

        self.init_ui()

    def _parse_config(self):
        vals = {}
        if not self.cf:
            return vals

        lines = self.cf.lines
        in_blur_block = False
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Detect blur block
            if stripped.startswith("blur:"):
                in_blur_block = True
                continue
            if in_blur_block:
                if stripped.startswith("}"):
                    in_blur_block = False
                    continue
                # parse method or strength
                m = re.match(r'method\s*=\s*["\']?(\w+)["\']?;', stripped)
                if m:
                    vals["blur-method"] = m.group(1)
                m2 = re.match(r'strength\s*=\s*(\d+);', stripped)
                if m2:
                    vals["blur-strength"] = int(m2.group(1))
                continue

            # parse key = value;
            m = re.match(r'(\w[\w-]*)\s*=\s*(.*);', stripped)
            if m:
                key, val = m.groups()
                key = key.strip()
                val = val.strip()
                if key in self.settings_defs:
                    t = self.settings_defs[key]
                    if t == "int":
                        vals[key] = int(float(val))
                    elif t == "float":
                        vals[key] = float(val)
                    elif t == "bool":
                        vals[key] = val.lower() in ("true", "1")
                    elif t == "str":
                        vals[key] = val.strip('"').strip("'")
        # set defaults for missing keys
        defaults = {
            "corner-radius": 10,
            "inactive-opacity": 0.7,
            "active-opacity": 1.0,
            "frame-opacity": 1.0,
            "fade-in-step": 0.03,
            "fade-out-step": 0.03,
            "fade-delta": 10,
            "fading": True,
            "shadow": True,
            "shadow-radius": 12,
            "shadow-opacity": 0.25,
            "blur-method": "dual_kawase",
            "blur-strength": 5
        }
        for k, v in defaults.items():
            if k not in vals:
                vals[k] = v

        return vals

    def init_ui(self):
        layout = QVBoxLayout()
        self.sliders = {}
        self.checkboxes = {}

        # Numeric sliders
        num_sliders = {
            "corner-radius": (0, 50),
            "inactive-opacity": (0, 100),  # scale 0-100
            "active-opacity": (0, 100),
            "frame-opacity": (0, 100),
            "fade-in-step": (0, 100),      # scale 0-1 to 0-100
            "fade-out-step": (0, 100),
            "fade-delta": (0, 100),
            "shadow-radius": (0, 50),
            "shadow-opacity": (0, 100),
            "blur-strength": (0, 50)
        }

        for key, (mn, mx) in num_sliders.items():
            val = self.settings[key]
            if isinstance(val, float) and val <= 1:  # scale small floats
                val = int(val * 100)
            layout.addLayout(self.create_slider(key, mn, mx, val))

        # Boolean checkboxes
        bool_keys = ["fading", "shadow"]
        for key in bool_keys:
            chk = QCheckBox(key)
            chk.setChecked(self.settings[key])
            chk.stateChanged.connect(lambda state, k=key: self.on_checkbox_change(k, state))
            layout.addWidget(chk)
            self.checkboxes[key] = chk

        # Blur method dropdown (simplified for now)
        # You could extend to QComboBox if desired
        lbl = QLabel(f"Blur method: {self.settings['blur-method']}")
        layout.addWidget(lbl)
        self.blur_label = lbl

        save_btn = QPushButton("Save Picom Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)
        self.setLayout(layout)

    def create_slider(self, key, min_val, max_val, init_val):
        layout = QHBoxLayout()
        lbl = QLabel(f"{key}: {init_val}")
        sld = QSlider(Qt.Orientation.Horizontal)
        sld.setRange(min_val, max_val)
        sld.setValue(init_val)
        sld.valueChanged.connect(lambda v, k=key, l=lbl: self.on_slider_change(k, v, l))
        layout.addWidget(lbl)
        layout.addWidget(sld)
        self.sliders[key] = sld
        return layout

    def on_slider_change(self, key, value, label):
        if key in ["inactive-opacity", "active-opacity", "frame-opacity", "fade-in-step", "fade-out-step", "shadow-opacity"]:
            self.settings[key] = value / 100
        else:
            self.settings[key] = value
        label.setText(f"{key}: {self.settings[key]}")

    def on_checkbox_change(self, key, state):
        self.settings[key] = state == Qt.CheckState.Checked

    def save_config(self):
        if not self.cf:
            QMessageBox.warning(self, "Error", "Picom config not loaded")
            return
        new_lines = []
        in_blur = False
        for line in self.cf.lines:
            stripped = line.strip()
            if stripped.startswith("blur:"):
                in_blur = True
                new_lines.append(line)
                continue
            if in_blur:
                if stripped.startswith("}"):
                    in_blur = False
                    new_lines.append(line)
                    continue
                # update blur settings
                if "method" in stripped:
                    new_lines.append(f'    method = "{self.settings["blur-method"]}";')
                elif "strength" in stripped:
                    new_lines.append(f'    strength = {self.settings["blur-strength"]};')
                else:
                    new_lines.append(line)
                continue

            m = re.match(r'(\w[\w-]*)\s*=\s*(.*);', stripped)
            if m:
                key = m.group(1).strip()
                if key in self.settings:
                    val = self.settings[key]
                    if isinstance(val, bool):
                        val = "true" if val else "false"
                    elif isinstance(val, float):
                        val = f"{val:.2f}"
                    new_lines.append(f"{key} = {val};")
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        self.cf.lines = new_lines
        self.cf.save()
        QMessageBox.information(self, "Saved", "Picom config saved!")

def create_editor(config=None):
    return EditorWidget(config)
