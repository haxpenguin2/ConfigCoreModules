# File: ~/.config_editor_packages/Picomsupport/plugin.py

from GUIconfigcore import ConfigFile  # import from your core
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QDoubleSpinBox, QPushButton, QCheckBox
)
from PyQt5.QtCore import Qt

class EditorWidget(QWidget):
    def __init__(self, config_path):
        super().__init__()
        self.config_path = config_path
        self.config = ConfigFile(config_path)
        self.settings = self._load_settings()
        self.init_ui()

    def _load_settings(self):
        cfg = self.config
        settings = {
            "backend": cfg.get("backend", "glx"),
            "vsync": cfg.get("vsync", "true") == "true",
            "inactive-opacity": float(cfg.get("inactive-opacity", 0.7)),
            "active-opacity": float(cfg.get("active-opacity", 1.0)),
            "frame-opacity": float(cfg.get("frame-opacity", 1.0)),
            "corner-radius": int(cfg.get("corner-radius", 10)),
            "fading": cfg.get("fading", "true") == "true",
            "fade-in-step": float(cfg.get("fade-in-step", 0.03)),
            "fade-out-step": float(cfg.get("fade-out-step", 0.03)),
            "fade-delta": int(cfg.get("fade-delta", 10)),
            "blur-strength": int(cfg.get("blur.strength", 5)),
            "shadow": cfg.get("shadow", "true") == "true",
            "shadow-radius": int(cfg.get("shadow-radius", 12)),
            "shadow-opacity": float(cfg.get("shadow-opacity", 0.25)),
        }
        return settings

    def init_ui(self):
        layout = QVBoxLayout()

        # Example: Inactive opacity
        layout.addWidget(QLabel("Inactive Opacity"))
        self.inactive_opacity_spin = QDoubleSpinBox()
        self.inactive_opacity_spin.setRange(0.0, 1.0)
        self.inactive_opacity_spin.setSingleStep(0.01)
        self.inactive_opacity_spin.setValue(self.settings["inactive-opacity"])
        layout.addWidget(self.inactive_opacity_spin)

        # Active opacity
        layout.addWidget(QLabel("Active Opacity"))
        self.active_opacity_spin = QDoubleSpinBox()
        self.active_opacity_spin.setRange(0.0, 1.0)
        self.active_opacity_spin.setSingleStep(0.01)
        self.active_opacity_spin.setValue(self.settings["active-opacity"])
        layout.addWidget(self.active_opacity_spin)

        # Shadow checkbox
        self.shadow_checkbox = QCheckBox("Enable Shadows")
        self.shadow_checkbox.setChecked(self.settings["shadow"])
        layout.addWidget(self.shadow_checkbox)

        # Corner radius
        layout.addWidget(QLabel("Corner Radius"))
        self.corner_radius_spin = QDoubleSpinBox()
        self.corner_radius_spin.setRange(0, 50)
        self.corner_radius_spin.setValue(self.settings["corner-radius"])
        layout.addWidget(self.corner_radius_spin)

        # Save button
        self.save_btn = QPushButton("Save Config")
        self.save_btn.clicked.connect(self.save_config)
        layout.addWidget(self.save_btn)

        self.setLayout(layout)

    def save_config(self):
        # Only write changed settings to minimize damage
        self.config.set("inactive-opacity", str(self.inactive_opacity_spin.value()))
        self.config.set("active-opacity", str(self.active_opacity_spin.value()))
        self.config.set("shadow", "true" if self.shadow_checkbox.isChecked() else "false")
        self.config.set("corner-radius", str(int(self.corner_radius_spin.value())))
        self.config.save()
