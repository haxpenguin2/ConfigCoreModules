# ~/.config_editor_packages/Picomsupport/plugin.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QCheckBox,
    QPushButton, QGroupBox, QFormLayout, QSpinBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt
from pathlib import Path
import re

class EditorWidget(QWidget):
    def __init__(self, config=None, ConfigFileClass=None):
        super().__init__()
        self.config_path = str(Path.home() / ".config/picom.conf")
        self.config_file = None
        self.settings = {}
        self.ConfigFileClass = ConfigFileClass  # unused here, kept for API
        self.init_ui()
        self.load_config()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Backend / VSync
        backend_box = QGroupBox("Backend & VSync")
        backend_layout = QFormLayout()
        backend_box.setLayout(backend_layout)
        layout.addWidget(backend_box)

        self.backend_label = QLabel("")
        backend_layout.addRow("Backend:", self.backend_label)

        self.vsync_checkbox = QCheckBox("Enable VSync")
        backend_layout.addRow(self.vsync_checkbox)

        # Rounded corners
        corner_box = QGroupBox("Rounded Corners")
        corner_layout = QFormLayout()
        corner_box.setLayout(corner_layout)
        layout.addWidget(corner_box)

        self.corner_spin = QSpinBox()
        self.corner_spin.setRange(0, 100)
        corner_layout.addRow("Corner Radius:", self.corner_spin)

        # Opacity
        opacity_box = QGroupBox("Opacity")
        opacity_layout = QFormLayout()
        opacity_box.setLayout(opacity_layout)
        layout.addWidget(opacity_box)

        self.active_opacity = QDoubleSpinBox()
        self.active_opacity.setRange(0.0, 1.0)
        self.active_opacity.setSingleStep(0.05)
        opacity_layout.addRow("Active Opacity:", self.active_opacity)

        self.inactive_opacity = QDoubleSpinBox()
        self.inactive_opacity.setRange(0.0, 1.0)
        self.inactive_opacity.setSingleStep(0.05)
        opacity_layout.addRow("Inactive Opacity:", self.inactive_opacity)

        self.frame_opacity = QDoubleSpinBox()
        self.frame_opacity.setRange(0.0, 1.0)
        self.frame_opacity.setSingleStep(0.05)
        opacity_layout.addRow("Frame Opacity:", self.frame_opacity)

        # Fade / transitions
        fade_box = QGroupBox("Fading & Transitions")
        fade_layout = QFormLayout()
        fade_box.setLayout(fade_layout)
        layout.addWidget(fade_box)

        self.fade_in = QDoubleSpinBox()
        self.fade_in.setRange(0.0, 1.0)
        self.fade_in.setSingleStep(0.01)
        fade_layout.addRow("Fade In Step:", self.fade_in)

        self.fade_out = QDoubleSpinBox()
        self.fade_out.setRange(0.0, 1.0)
        self.fade_out.setSingleStep(0.01)
        fade_layout.addRow("Fade Out Step:", self.fade_out)

        self.fade_delta = QSpinBox()
        self.fade_delta.setRange(0, 1000)
        fade_layout.addRow("Fade Delta (ms):", self.fade_delta)

        self.fading_enabled = QCheckBox("Enable Fading")
        fade_layout.addRow(self.fading_enabled)

        # Blur
        blur_box = QGroupBox("Blur")
        blur_layout = QFormLayout()
        blur_box.setLayout(blur_layout)
        layout.addWidget(blur_box)

        self.blur_method_label = QLabel("")
        blur_layout.addRow("Method:", self.blur_method_label)

        self.blur_strength = QSpinBox()
        self.blur_strength.setRange(0, 50)
        blur_layout.addRow("Strength:", self.blur_strength)

        # Shadows
        shadow_box = QGroupBox("Shadows")
        shadow_layout = QFormLayout()
        shadow_box.setLayout(shadow_layout)
        layout.addWidget(shadow_box)

        self.shadow_enabled = QCheckBox("Enable Shadow")
        shadow_layout.addRow(self.shadow_enabled)

        self.shadow_radius = QSpinBox()
        self.shadow_radius.setRange(0, 50)
        shadow_layout.addRow("Shadow Radius:", self.shadow_radius)

        self.shadow_opacity = QDoubleSpinBox()
        self.shadow_opacity.setRange(0.0, 1.0)
        self.shadow_opacity.setSingleStep(0.01)
        shadow_layout.addRow("Shadow Opacity:", self.shadow_opacity)

        # Save button
        save_btn = QPushButton("Save Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)

    def load_config(self):
        if not Path(self.config_path).exists():
            return
        with open(self.config_path, "r") as f:
            text = f.read()

        # regex patterns for settings
        self.settings["backend"] = re.search(r'backend\s*=\s*"(\w+)"', text)
        self.settings["backend"] = self.settings["backend"].group(1) if self.settings["backend"] else "glx"

        self.settings["vsync"] = "true" in text

        self.settings["corner-radius"] = int(re.search(r'corner-radius\s*=\s*(\d+)', text).group(1)) if re.search(r'corner-radius\s*=\s*(\d+)', text) else 0

        for key in ["active-opacity", "inactive-opacity", "frame-opacity",
                    "fade-in-step", "fade-out-step", "fade-delta",
                    "blur-strength", "shadow-radius", "shadow-opacity"]:
            match = re.search(rf'{key.replace("-", "_")}? = ([0-9.]+)', text)
            if match:
                self.settings[key] = float(match.group(1))
            else:
                self.settings[key] = 1.0

        self.settings["fading"] = "true" in text
        self.settings["shadow"] = "true" in text

        self.settings["blur_method"] = re.search(r'method\s*=\s*"(\w+)"', text)
        self.settings["blur_method"] = self.settings["blur_method"].group(1) if self.settings["blur_method"] else "dual_kawase"

        # populate UI
        self.backend_label.setText(self.settings["backend"])
        self.vsync_checkbox.setChecked(self.settings["vsync"])
        self.corner_spin.setValue(self.settings["corner-radius"])
        self.active_opacity.setValue(self.settings.get("active-opacity", 1.0))
        self.inactive_opacity.setValue(self.settings.get("inactive-opacity", 0.7))
        self.frame_opacity.setValue(self.settings.get("frame-opacity", 1.0))
        self.fade_in.setValue(self.settings.get("fade-in-step", 0.03))
        self.fade_out.setValue(self.settings.get("fade-out-step", 0.03))
        self.fade_delta.setValue(int(self.settings.get("fade-delta", 10)))
        self.fading_enabled.setChecked(self.settings.get("fading", True))
        self.blur_method_label.setText(self.settings.get("blur_method", "dual_kawase"))
        self.blur_strength.setValue(int(self.settings.get("strength", 5)))
        self.shadow_enabled.setChecked(self.settings.get("shadow", True))
        self.shadow_radius.setValue(int(self.settings.get("shadow-radius", 12)))
        self.shadow_opacity.setValue(float(self.settings.get("shadow-opacity", 0.25)))

    def save_config(self):
        lines = []
        lines.append(f'backend = "{self.settings.get("backend", "glx")}"')
        lines.append(f'vsync = {"true" if self.vsync_checkbox.isChecked() else "false"}\n')
        lines.append(f'corner-radius = {self.corner_spin.value()}\n')
        lines.append(f'inactive-opacity = {self.inactive_opacity.value()}')
        lines.append(f'active-opacity = {self.active_opacity.value()}')
        lines.append(f'frame-opacity = {self.frame_opacity.value()}\n')
        lines.append(f'fade-in-step = {self.fade_in.value()}')
        lines.append(f'fade-out-step = {self.fade_out.value()}')
        lines.append(f'fade-delta = {self.fade_delta.value()}')
        lines.append(f'fading = {"true" if self.fading_enabled.isChecked() else "false"}\n')
        lines.append('blur:\n{')
        lines.append(f'    method = "{self.blur_method_label.text()}";')
        lines.append(f'    strength = {self.blur_strength.value()};')
        lines.append('};\n')
        lines.append(f'shadow = {"true" if self.shadow_enabled.isChecked() else "false"}')
        lines.append(f'shadow-radius = {self.shadow_radius.value()}')
        lines.append(f'shadow-opacity = {self.shadow_opacity.value()}')

        with open(self.config_path, "w") as f:
            f.write("\n".join(lines))

