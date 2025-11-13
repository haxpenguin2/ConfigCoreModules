# Picom plugin for GUIconfigcore
# Compatible with your GUI core

# Use the core’s ConfigFile (absolute import)
from GUIconfigcore import ConfigFile
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QDoubleSpinBox, QPushButton
)

class EditorWidget(QWidget):
    def __init__(self, core_config):
        super().__init__()
        self.core_config = core_config
        self.config_path = core_config.config_path  # path to picom.conf
        self.settings = {}
        self.load_config()
        self.init_ui()

    def load_config(self):
        # Load Picom config using core’s ConfigFile
        cf = ConfigFile(self.config_path)
        self.settings = {
            "inactive-opacity": float(cf.get("inactive-opacity", 0.7)),
            "active-opacity": float(cf.get("active-opacity", 1.0)),
            "fade-in-step": float(cf.get("fade-in-step", 0.03)),
            "fade-out-step": float(cf.get("fade-out-step", 0.03)),
        }

    def init_ui(self):
        layout = QVBoxLayout()

        # Inactive opacity
        layout.addWidget(QLabel("Inactive window opacity"))
        self.inactive_opacity_spin = QDoubleSpinBox()
        self.inactive_opacity_spin.setRange(0.0, 1.0)
        self.inactive_opacity_spin.setSingleStep(0.05)
        self.inactive_opacity_spin.setValue(self.settings["inactive-opacity"])
        layout.addWidget(self.inactive_opacity_spin)

        # Active opacity
        layout.addWidget(QLabel("Active window opacity"))
        self.active_opacity_spin = QDoubleSpinBox()
        self.active_opacity_spin.setRange(0.0, 1.0)
        self.active_opacity_spin.setSingleStep(0.05)
        self.active_opacity_spin.setValue(self.settings["active-opacity"])
        layout.addWidget(self.active_opacity_spin)

        # Fade-in step
        layout.addWidget(QLabel("Fade-in step"))
        self.fade_in_spin = QDoubleSpinBox()
        self.fade_in_spin.setRange(0.0, 1.0)
        self.fade_in_spin.setSingleStep(0.01)
        self.fade_in_spin.setValue(self.settings["fade-in-step"])
        layout.addWidget(self.fade_in_spin)

        # Fade-out step
        layout.addWidget(QLabel("Fade-out step"))
        self.fade_out_spin = QDoubleSpinBox()
        self.fade_out_spin.setRange(0.0, 1.0)
        self.fade_out_spin.setSingleStep(0.01)
        self.fade_out_spin.setValue(self.settings["fade-out-step"])
        layout.addWidget(self.fade_out_spin)

        # Save button
        save_btn = QPushButton("Save Picom Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)

        self.setLayout(layout)

    def save_config(self):
        cf = ConfigFile(self.config_path)
        cf.set("inactive-opacity", str(self.inactive_opacity_spin.value()))
        cf.set("active-opacity", str(self.active_opacity_spin.value()))
        cf.set("fade-in-step", str(self.fade_in_spin.value()))
        cf.set("fade-out-step", str(self.fade_out_spin.value()))
        cf.save()
