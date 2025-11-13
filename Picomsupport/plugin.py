# ~/.config_editor_packages/Picomsupport/plugin.py
from PyQt6.QtWidgets import *
from PyQt6.QtCore import Qt
from pathlib import Path
import re

class EditorWidget(QWidget):
    def __init__(self, config=None):
        super().__init__()
        # Path to picom config
        self.config_path = Path.home() / ".config/picom.conf"
        self.lines = []
        self.init_ui()
        self.load_config()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Backend
        layout.addWidget(QLabel("Backend:"))
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["xrender", "glx", "xr_glx_hybrid"])
        layout.addWidget(self.backend_combo)

        # VSync
        self.vsync_checkbox = QCheckBox("Enable VSync")
        layout.addWidget(self.vsync_checkbox)

        # Rounded corners
        layout.addWidget(QLabel("Corner Radius:"))
        self.corner_spin = QSpinBox()
        self.corner_spin.setRange(0, 100)
        layout.addWidget(self.corner_spin)

        # Opacity
        layout.addWidget(QLabel("Inactive Opacity:"))
        self.inactive_opacity = QDoubleSpinBox()
        self.inactive_opacity.setRange(0.0, 1.0)
        self.inactive_opacity.setSingleStep(0.05)
        layout.addWidget(self.inactive_opacity)

        layout.addWidget(QLabel("Active Opacity:"))
        self.active_opacity = QDoubleSpinBox()
        self.active_opacity.setRange(0.0, 1.0)
        self.active_opacity.setSingleStep(0.05)
        layout.addWidget(self.active_opacity)

        layout.addWidget(QLabel("Frame Opacity:"))
        self.frame_opacity = QDoubleSpinBox()
        self.frame_opacity.setRange(0.0, 1.0)
        self.frame_opacity.setSingleStep(0.05)
        layout.addWidget(self.frame_opacity)

        # Fade
        self.fading_checkbox = QCheckBox("Enable fading")
        layout.addWidget(self.fading_checkbox)

        layout.addWidget(QLabel("Fade in step:"))
        self.fade_in = QDoubleSpinBox()
        self.fade_in.setRange(0.0, 1.0)
        self.fade_in.setSingleStep(0.01)
        layout.addWidget(self.fade_in)

        layout.addWidget(QLabel("Fade out step:"))
        self.fade_out = QDoubleSpinBox()
        self.fade_out.setRange(0.0, 1.0)
        self.fade_out.setSingleStep(0.01)
        layout.addWidget(self.fade_out)

        layout.addWidget(QLabel("Fade delta (ms):"))
        self.fade_delta = QSpinBox()
        self.fade_delta.setRange(1, 1000)
        layout.addWidget(self.fade_delta)

        # Blur
        self.blur_checkbox = QCheckBox("Enable Blur")
        layout.addWidget(self.blur_checkbox)
        layout.addWidget(QLabel("Blur strength:"))
        self.blur_strength = QSpinBox()
        self.blur_strength.setRange(1, 50)
        layout.addWidget(self.blur_strength)

        # Shadows
        self.shadow_checkbox = QCheckBox("Enable Shadows")
        layout.addWidget(self.shadow_checkbox)
        layout.addWidget(QLabel("Shadow radius:"))
        self.shadow_radius = QSpinBox()
        self.shadow_radius.setRange(0, 50)
        layout.addWidget(self.shadow_radius)
        layout.addWidget(QLabel("Shadow opacity:"))
        self.shadow_opacity = QDoubleSpinBox()
        self.shadow_opacity.setRange(0.0, 1.0)
        self.shadow_opacity.setSingleStep(0.01)
        layout.addWidget(self.shadow_opacity)

        # Save button
        save_btn = QPushButton("Save Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)

    def load_config(self):
        if not self.config_path.exists():
            return

        with open(self.config_path, "r") as f:
            self.lines = f.readlines()

        for line in self.lines:
            line_clean = line.split("#")[0].strip()  # remove comments
            if not line_clean:
                continue
            if "backend" in line_clean:
                for i in range(self.backend_combo.count()):
                    if self.backend_combo.itemText(i) in line_clean:
                        self.backend_combo.setCurrentIndex(i)
            elif "vsync" in line_clean:
                self.vsync_checkbox.setChecked("true" in line_clean)
            elif "corner-radius" in line_clean:
                m = re.search(r'(\d+)', line_clean)
                if m: self.corner_spin.setValue(int(m.group(1)))
            elif "inactive-opacity" in line_clean:
                m = re.search(r'([0-9.]+)', line_clean)
                if m: self.inactive_opacity.setValue(float(m.group(1)))
            elif "active-opacity" in line_clean:
                m = re.search(r'([0-9.]+)', line_clean)
                if m: self.active_opacity.setValue(float(m.group(1)))
            elif "frame-opacity" in line_clean:
                m = re.search(r'([0-9.]+)', line_clean)
                if m: self.frame_opacity.setValue(float(m.group(1)))
            elif "fading" in line_clean:
                self.fading_checkbox.setChecked("true" in line_clean)
            elif "fade-in-step" in line_clean:
                m = re.search(r'([0-9.]+)', line_clean)
                if m: self.fade_in.setValue(float(m.group(1)))
            elif "fade-out-step" in line_clean:
                m = re.search(r'([0-9.]+)', line_clean)
                if m: self.fade_out.setValue(float(m.group(1)))
            elif "fade-delta" in line_clean:
                m = re.search(r'(\d+)', line_clean)
                if m: self.fade_delta.setValue(int(m.group(1)))
            elif "strength" in line_clean and "blur" in line_clean:
                m = re.search(r'(\d+)', line_clean)
                if m: self.blur_strength.setValue(int(m.group(1)))
            elif "blur" in line_clean:
                self.blur_checkbox.setChecked(True)
            elif "shadow" in line_clean and "true" in line_clean:
                self.shadow_checkbox.setChecked(True)
            elif "shadow-radius" in line_clean:
                m = re.search(r'(\d+)', line_clean)
                if m: self.shadow_radius.setValue(int(m.group(1)))
            elif "shadow-opacity" in line_clean:
                m = re.search(r'([0-9.]+)', line_clean)
                if m: self.shadow_opacity.setValue(float(m.group(1)))

    def save_config(self):
        new_lines = []
        for line in self.lines:
            line_clean = line.split("#")[0].strip()
            if "backend" in line_clean:
                new_lines.append(f'backend = "{self.backend_combo.currentText()}";\n')
            elif "vsync" in line_clean:
                new_lines.append(f'vsync = {"true" if self.vsync_checkbox.isChecked() else "false"};\n')
            elif "corner-radius" in line_clean:
                new_lines.append(f'corner-radius = {self.corner_spin.value()};\n')
            elif "inactive-opacity" in line_clean:
                new_lines.append(f'inactive-opacity = {self.inactive_opacity.value()};\n')
            elif "active-opacity" in line_clean:
                new_lines.append(f'active-opacity = {self.active_opacity.value()};\n')
            elif "frame-opacity" in line_clean:
                new_lines.append(f'frame-opacity = {self.frame_opacity.value()};\n')
            elif "fading" in line_clean:
                new_lines.append(f'fading = {"true" if self.fading_checkbox.isChecked() else "false"};\n')
            elif "fade-in-step" in line_clean:
                new_lines.append(f'fade-in-step = {self.fade_in.value()};\n')
            elif "fade-out-step" in line_clean:
                new_lines.append(f'fade-out-step = {self.fade_out.value()};\n')
            elif "fade-delta" in line_clean:
                new_lines.append(f'fade-delta = {self.fade_delta.value()};\n')
            elif "strength" in line_clean and "blur" in line_clean:
                new_lines.append(f'    strength = {self.blur_strength.value()};\n')
            elif "blur" in line_clean:
                new_lines.append("blur:\n{\n")
            elif "shadow" in line_clean and "true" in line_clean:
                new_lines.append(f'shadow = {"true" if self.shadow_checkbox.isChecked() else "false"};\n')
            elif "shadow-radius" in line_clean:
                new_lines.append(f'shadow-radius = {self.shadow_radius.value()};\n')
            elif "shadow-opacity" in line_clean:
                new_lines.append(f'shadow-opacity = {self.shadow_opacity.value()};\n')
            else:
                new_lines.append(line)

        # Save safely
        with open(self.config_path, "w") as f:
            f.writelines(new_lines)
