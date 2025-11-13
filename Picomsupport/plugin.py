#!/usr/bin/env python3
"""
Picom Config Editor Plugin
"""

import sys
import os
from pathlib import Path
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QCheckBox, QMessageBox, QSpinBox, QDoubleSpinBox, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt

# Dynamically import ConfigFile from core
core_path = Path(__file__).resolve().parent.parent  # adjust for plugin location
sys.path.insert(0, str(core_path))
from config_core import ConfigFile

# -------------------------
# Picom Editor Widget
# -------------------------
class EditorWidget(QWidget):
    def __init__(self, config: ConfigFile = None):
        super().__init__()
        self.config_path = Path.home() / ".config/picom.conf"
        self.cf: ConfigFile = None
        self.settings = {
            "backend": "glx",
            "vsync": True,
            "corner-radius": 10,
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
            "shadow-opacity": 0.25
        }

        self._parse_config()
        self.init_ui()

    # -------------------------
    # Load existing config
    # -------------------------
    def _parse_config(self):
        if not self.config_path.exists():
            return
        lines = self.config_path.read_text().splitlines()
        for l in lines:
            # remove comments
            line = l.split("#")[0].strip()
            if not line:
                continue
            try:
                # simple assignments: key = value;
                m = re.match(r"([a-zA-Z0-9_-]+)\s*=\s*(.+);?", line)
                if m:
                    k, v = m.groups()
                    k = k.strip()
                    v = v.strip().strip('"')
                    if k in ("vsync", "fading", "shadow"):
                        self.settings[k] = v.lower() == "true"
                    elif k in ("corner-radius", "blur-strength", "shadow-radius", "fade-delta"):
                        self.settings[k] = int(float(v))
                    elif k in ("inactive-opacity", "active-opacity", "frame-opacity", "fade-in-step", "fade-out-step"):
                        self.settings[k] = float(v)
                    elif k == "backend":
                        self.settings[k] = v
                    elif k == "method":  # inside blur block
                        self.settings["blur-method"] = v
            except Exception:
                continue

    # -------------------------
    # Build GUI
    # -------------------------
    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Backend
        backend_box = QGroupBox("Backend")
        backend_layout = QHBoxLayout()
        backend_box.setLayout(backend_layout)
        self.backend_label = QLabel(self.settings["backend"])
        backend_layout.addWidget(QLabel("Backend:"))
        backend_layout.addWidget(self.backend_label)
        layout.addWidget(backend_box)

        # VSync & Fading & Shadow
        self.vsync_cb = QCheckBox("Enable VSync")
        self.vsync_cb.setChecked(self.settings["vsync"])
        self.fading_cb = QCheckBox("Enable Fading")
        self.fading_cb.setChecked(self.settings["fading"])
        self.shadow_cb = QCheckBox("Enable Shadows")
        self.shadow_cb.setChecked(self.settings["shadow"])
        layout.addWidget(self.vsync_cb)
        layout.addWidget(self.fading_cb)
        layout.addWidget(self.shadow_cb)

        # Rounded corners
        self.corner_spin = QSpinBox()
        self.corner_spin.setRange(0, 100)
        self.corner_spin.setValue(self.settings["corner-radius"])
        layout.addWidget(QLabel("Corner radius:"))
        layout.addWidget(self.corner_spin)

        # Opacity
        self.inactive_opacity = QDoubleSpinBox()
        self.inactive_opacity.setRange(0.0, 1.0)
        self.inactive_opacity.setSingleStep(0.01)
        self.inactive_opacity.setValue(self.settings["inactive-opacity"])
        self.active_opacity = QDoubleSpinBox()
        self.active_opacity.setRange(0.0, 1.0)
        self.active_opacity.setSingleStep(0.01)
        self.active_opacity.setValue(self.settings["active-opacity"])
        self.frame_opacity = QDoubleSpinBox()
        self.frame_opacity.setRange(0.0, 1.0)
        self.frame_opacity.setSingleStep(0.01)
        self.frame_opacity.setValue(self.settings["frame-opacity"])

        opacity_layout = QFormLayout()
        opacity_layout.addRow("Inactive opacity:", self.inactive_opacity)
        opacity_layout.addRow("Active opacity:", self.active_opacity)
        opacity_layout.addRow("Frame opacity:", self.frame_opacity)
        opacity_group = QGroupBox("Opacity Settings")
        opacity_group.setLayout(opacity_layout)
        layout.addWidget(opacity_group)

        # Fade
        fade_layout = QFormLayout()
        self.fade_in_step = QDoubleSpinBox()
        self.fade_in_step.setRange(0.001, 1.0)
        self.fade_in_step.setSingleStep(0.01)
        self.fade_in_step.setValue(self.settings["fade-in-step"])
        self.fade_out_step = QDoubleSpinBox()
        self.fade_out_step.setRange(0.001, 1.0)
        self.fade_out_step.setSingleStep(0.01)
        self.fade_out_step.setValue(self.settings["fade-out-step"])
        self.fade_delta = QSpinBox()
        self.fade_delta.setRange(1, 100)
        self.fade_delta.setValue(self.settings["fade-delta"])
        fade_layout.addRow("Fade-in step:", self.fade_in_step)
        fade_layout.addRow("Fade-out step:", self.fade_out_step)
        fade_layout.addRow("Fade delta (ms):", self.fade_delta)
        fade_group = QGroupBox("Fade Settings")
        fade_group.setLayout(fade_layout)
        layout.addWidget(fade_group)

        # Blur
        blur_layout = QFormLayout()
        self.blur_method_label = QLabel(self.settings["blur-method"])
        self.blur_strength = QSpinBox()
        self.blur_strength.setRange(0, 50)
        self.blur_strength.setValue(self.settings["blur-strength"])
        blur_layout.addRow("Blur method:", self.blur_method_label)
        blur_layout.addRow("Blur strength:", self.blur_strength)
        blur_group = QGroupBox("Blur Settings")
        blur_group.setLayout(blur_layout)
        layout.addWidget(blur_group)

        # Shadow
        shadow_layout = QFormLayout()
        self.shadow_radius = QSpinBox()
        self.shadow_radius.setRange(0, 50)
        self.shadow_radius.setValue(self.settings["shadow-radius"])
        self.shadow_opacity = QDoubleSpinBox()
        self.shadow_opacity.setRange(0.0, 1.0)
        self.shadow_opacity.setSingleStep(0.01)
        self.shadow_opacity.setValue(self.settings["shadow-opacity"])
        shadow_layout.addRow("Shadow radius:", self.shadow_radius)
        shadow_layout.addRow("Shadow opacity:", self.shadow_opacity)
        shadow_group = QGroupBox("Shadow Settings")
        shadow_group.setLayout(shadow_layout)
        layout.addWidget(shadow_group)

        # Save button
        save_btn = QPushButton("Save Picom Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)
        layout.addStretch()

    # -------------------------
    # Save config
    # -------------------------
    def save_config(self):
        if not self.cf:
            # create in-memory ConfigFile
            self.cf = ConfigFile(self.config_path) if self.config_path.exists() else ConfigFile(str(self.config_path))
        # rebuild lines
        lines = []
        lines.append(f'backend = "{self.settings["backend"]}";')
        lines.append(f'vsync = {"true" if self.vsync_cb.isChecked() else "false"};')
        lines.append(f'corner-radius = {self.corner_spin.value()};')
        lines.append(f'inactive-opacity = {self.inactive_opacity.value()};')
        lines.append(f'active-opacity = {self.active_opacity.value()};')
        lines.append(f'frame-opacity = {self.frame_opacity.value()};')
        lines.append(f'fade-in-step = {self.fade_in_step.value()};')
        lines.append(f'fade-out-step = {self.fade_out_step.value()};')
        lines.append(f'fade-delta = {self.fade_delta.value()};')
        lines.append(f'fading = {"true" if self.fading_cb.isChecked() else "false"};')
        lines.append("blur:")
        lines.append("{")
        lines.append(f'    method = "{self.settings["blur-method"]}";')
        lines.append(f'    strength = {self.blur_strength.value()};')
        lines.append("};")
        lines.append(f'shadow = {"true" if self.shadow_cb.isChecked() else "false"};')
        lines.append(f'shadow-radius = {self.shadow_radius.value()};')
        lines.append(f'shadow-opacity = {self.shadow_opacity.value()};')

        self.cf.lines = lines
        backup = self.cf.save(backup=True)
        QMessageBox.information(self, "Saved", f"Picom config saved!\nBackup: {backup}")
