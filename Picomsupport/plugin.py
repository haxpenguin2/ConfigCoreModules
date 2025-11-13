# plugin.py
# Picom Editor Plugin for GUIconfigcore
# Fully compatible with CoreGUI, delayed UI init to avoid QApplication crash

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QDoubleSpinBox, QPushButton, QCheckBox

# Import your core's ConfigFile system
from config_core import ConfigFile

class EditorWidget(QWidget):
    def __init__(self, config_path):
        super().__init__()
        self.config_path = config_path
        self.config = ConfigFile(config_path)
        self.settings = self._load_settings()

        self._ui_initialized = False  # ensure init_ui runs only once

    def _load_settings(self):
        cfg = self.config
        return {
            "inactive-opacity": float(cfg.get("inactive-opacity", 0.7)),
            "active-opacity": float(cfg.get("active-opacity", 1.0)),
            "shadow": cfg.get("shadow", "true") == "true",
            "corner-radius": int(cfg.get("corner-radius", 10)),
        }

    def init_ui(self):
        if self._ui_initialized:
            return  # prevent double init

        layout = QVBoxLayout()

        # Inactive opacity
        self.inactive_opacity_spin = QDoubleSpinBox()
        self.inactive_opacity_spin.setRange(0.0, 1.0)
        self.inactive_opacity_spin.setSingleStep(0.01)
        self.inactive_opacity_spin.setValue(self.settings["inactive-opacity"])
        layout.addWidget(QLabel("Inactive Opacity"))
        layout.addWidget(self.inactive_opacity_spin)

        # Active opacity
        self.active_opacity_spin = QDoubleSpinBox()
        self.active_opacity_spin.setRange(0.0, 1.0)
        self.active_opacity_spin.setSingleStep(0.01)
        self.active_opacity_spin.setValue(self.settings["active-opacity"])
        layout.addWidget(QLabel("Active Opacity"))
        layout.addWidget(self.active_opacity_spin)

        # Shadow checkbox
        self.shadow_checkbox = QCheckBox("Enable Shadows")
        self.shadow_checkbox.setChecked(self.settings["shadow"])
        layout.addWidget(self.shadow_checkbox)

        # Corner radius
        self.corner_radius_spin = QDoubleSpinBox()
        self.corner_radius_spin.setRange(0, 50)
        self.corner_radius_spin.setValue(self.settings["corner-radius"])
        layout.addWidget(QLabel("Corner Radius"))
        layout.addWidget(self.corner_radius_spin)

        # Save button
        self.save_btn = QPushButton("Save Config")
        self.save_btn.clicked.connect(self.save_config)
        layout.addWidget(self.save_btn)

        self.setLayout(layout)
        self._ui_initialized = True

    def save_config(self):
        self.config.set("inactive-opacity", str(self.inactive_opacity_spin.value()))
        self.config.set("active-opacity", str(self.active_opacity_spin.value()))
        self.config.set("shadow", "true" if self.shadow_checkbox.isChecked() else "false")
        self.config.set("corner-radius", str(int(self.corner_radius_spin.value())))
        self.config.save()
