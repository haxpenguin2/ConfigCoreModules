from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSlider, QCheckBox, QPushButton, QHBoxLayout, QFileDialog
)
from PyQt6.QtCore import Qt
import configparser
import os

class EditorWidget(QWidget):
    def __init__(self, config=None):
        super().__init__()
        self.setWindowTitle("Picom Config Editor")
        self.config_file = os.path.expanduser("~/.config/picom/picom.conf")
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Load current config or create defaults
        self.config = self.load_config()

        # --- Blur slider ---
        self.blur_label = QLabel(f"Blur radius: {self.config['blur-radius']}")
        self.blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_slider.setRange(0, 50)
        self.blur_slider.setValue(int(self.config['blur-radius']))
        self.blur_slider.valueChanged.connect(lambda val: self.blur_label.setText(f"Blur radius: {val}"))
        self.layout.addWidget(self.blur_label)
        self.layout.addWidget(self.blur_slider)

        # --- Shadow slider ---
        self.shadow_label = QLabel(f"Shadow opacity: {self.config['shadow-opacity']}")
        self.shadow_slider = QSlider(Qt.Orientation.Horizontal)
        self.shadow_slider.setRange(0, 100)
        self.shadow_slider.setValue(int(float(self.config['shadow-opacity']) * 100))
        self.shadow_slider.valueChanged.connect(lambda val: self.shadow_label.setText(f"Shadow opacity: {val/100:.2f}"))
        self.layout.addWidget(self.shadow_label)
        self.layout.addWidget(self.shadow_slider)

        # --- Rounded corners slider ---
        self.corner_label = QLabel(f"Corner radius: {self.config['corner-radius']}")
        self.corner_slider = QSlider(Qt.Orientation.Horizontal)
        self.corner_slider.setRange(0, 50)
        self.corner_slider.setValue(int(self.config['corner-radius']))
        self.corner_slider.valueChanged.connect(lambda val: self.corner_label.setText(f"Corner radius: {val}"))
        self.layout.addWidget(self.corner_label)
        self.layout.addWidget(self.corner_slider)

        # --- Fading checkbox ---
        self.fade_checkbox = QCheckBox("Enable fade")
        self.fade_checkbox.setChecked(self.config['fading'])
        self.layout.addWidget(self.fade_checkbox)

        # --- Transparency rules button ---
        self.transparency_btn = QPushButton("Edit transparency rules")
        self.transparency_btn.clicked.connect(self.edit_transparency)
        self.layout.addWidget(self.transparency_btn)

        # --- Save button ---
        self.save_btn = QPushButton("Save Picom Config")
        self.save_btn.clicked.connect(self.save_config)
        self.layout.addWidget(self.save_btn)

    def load_config(self):
        """Load picom.conf or return defaults"""
        defaults = {
            "blur-radius": "10",
            "shadow-opacity": "0.75",
            "corner-radius": "5",
            "fading": True,
            "transparency-rules": []
        }
        if not os.path.exists(self.config_file):
            return defaults

        config_dict = defaults.copy()
        with open(self.config_file, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or line == "":
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key in config_dict:
                        if key == "fading":
                            config_dict[key] = value.lower() in ("true", "yes", "1")
                        else:
                            config_dict[key] = value
        return config_dict

    def edit_transparency(self):
        # This can pop up a dialog to edit rules, for now we just mock
        print("Transparency rules editor would open here!")

    def save_config(self):
        with open(self.config_file, "w") as f:
            f.write(f"blur-radius = {self.blur_slider.value()}\n")
            f.write(f"shadow-opacity = {self.shadow_slider.value()/100:.2f}\n")
            f.write(f"corner-radius = {self.corner_slider.value()}\n")
            f.write(f"fading = {'true' if self.fade_checkbox.isChecked() else 'false'}\n")
            # Here you would write transparency rules too
        print(f"Saved config to {self.config_file}")
