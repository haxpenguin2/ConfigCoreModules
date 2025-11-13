from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QDoubleSpinBox, QCheckBox, QPushButton, QSlider, QHBoxLayout

# Dummy ConfigFile loader you already have
from config_core import ConfigFile

class EditorWidget(QWidget):
    def __init__(self, config_path):
        super().__init__()
        self.config = ConfigFile(config_path)
        self.settings = self._load_settings()
        self.init_ui()

    def _load_settings(self):
        """Load config values safely, convert numbers where needed."""
        s = self.config.get_all()  # returns dict of config
        safe_settings = {}

        # Opacity/fade values
        for key in ["inactive-opacity", "active-opacity", "frame-opacity",
                    "fade-in-step", "fade-out-step", "fade-delta", "blur-strength",
                    "corner-radius", "shadow-radius", "shadow-opacity"]:
            val = s.get(key, 0)
            try:
                safe_settings[key] = float(val)
            except (ValueError, TypeError):
                safe_settings[key] = 0.0

        # Booleans
        for key in ["fading", "blur-enabled", "shadow-enabled", "rounded-corners", "vsync"]:
            val = s.get(key, "false")
            safe_settings[key] = str(val).lower() in ["1", "true", "yes"]

        return safe_settings

    def init_ui(self):
        layout = QVBoxLayout()

        # Example: inactive opacity
        layout.addWidget(QLabel("Inactive Opacity"))
        self.inactive_opacity_spin = QDoubleSpinBox()
        self.inactive_opacity_spin.setRange(0.0, 1.0)
        self.inactive_opacity_spin.setSingleStep(0.01)
        self.inactive_opacity_spin.setValue(self.settings.get("inactive-opacity", 0.7))
        layout.addWidget(self.inactive_opacity_spin)

        # Active opacity
        layout.addWidget(QLabel("Active Opacity"))
        self.active_opacity_spin = QDoubleSpinBox()
        self.active_opacity_spin.setRange(0.0, 1.0)
        self.active_opacity_spin.setSingleStep(0.01)
        self.active_opacity_spin.setValue(self.settings.get("active-opacity", 1.0))
        layout.addWidget(self.active_opacity_spin)

        # Fading checkbox
        self.fading_checkbox = QCheckBox("Enable Fading")
        self.fading_checkbox.setChecked(self.settings.get("fading", True))
        layout.addWidget(self.fading_checkbox)

        # Rounded corners
        self.rounded_checkbox = QCheckBox("Rounded Corners")
        self.rounded_checkbox.setChecked(self.settings.get("rounded-corners", True))
        layout.addWidget(self.rounded_checkbox)

        # Save button
        save_btn = QPushButton("Save Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)

        self.setLayout(layout)

    def save_config(self):
        """Write changes back to config safely"""
        self.config.set("inactive-opacity", str(self.inactive_opacity_spin.value()))
        self.config.set("active-opacity", str(self.active_opacity_spin.value()))
        self.config.set("fading", str(self.fading_checkbox.isChecked()).lower())
        self.config.set("rounded-corners", str(self.rounded_checkbox.isChecked()).lower())
        self.config.write()  # commits changes to file
