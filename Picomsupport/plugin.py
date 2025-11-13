# plugin.py
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout,
    QSlider, QPushButton, QCheckBox
)
from PyQt6.QtCore import Qt
import shutil

# Import ConfigFile from your GUI core
from config_core import ConfigFile

PICOM_PATH = str(Path.home() / ".config/picom.conf")


class EditorWidget(QWidget):
    def __init__(self, config: ConfigFile):
        super().__init__()
        self.config = config  # this is a ConfigFile instance
        self._parse_config()
        self.init_ui()

    def _parse_config(self):
        """Load current settings from picom.conf into variables."""
        self.settings = {
            "backend": "glx",
            "vsync": True,
            "corner-radius": 10,
            "inactive-opacity": 0.7,
            "active-opacity": 1.0,
            "frame-opacity": 1.0,
            "fading": True,
            "fade-in-step": 0.03,
            "fade-out-step": 0.03,
            "fade-delta": 10,
            "blur-strength": 5,
            "shadow": True,
            "shadow-radius": 12,
            "shadow-opacity": 0.25
        }

        # read current values from config if exists
        if self.config:
            for line in self.config.lines:
                line = line.strip()
                if line.startswith("backend"):
                    self.settings["backend"] = line.split("=")[1].strip().strip('";')
                elif line.startswith("vsync"):
                    self.settings["vsync"] = line.split("=")[1].strip().strip(";").lower() == "true"
                elif line.startswith("corner-radius"):
                    self.settings["corner-radius"] = int(line.split("=")[1].strip().strip(";"))
                elif line.startswith("inactive-opacity"):
                    self.settings["inactive-opacity"] = float(line.split("=")[1].strip().strip(";"))
                elif line.startswith("active-opacity"):
                    self.settings["active-opacity"] = float(line.split("=")[1].strip().strip(";"))
                elif line.startswith("frame-opacity"):
                    self.settings["frame-opacity"] = float(line.split("=")[1].strip().strip(";"))
                elif line.startswith("fade-in-step"):
                    self.settings["fade-in-step"] = float(line.split("=")[1].strip().strip(";"))
                elif line.startswith("fade-out-step"):
                    self.settings["fade-out-step"] = float(line.split("=")[1].strip().strip(";"))
                elif line.startswith("fade-delta"):
                    self.settings["fade-delta"] = int(line.split("=")[1].strip().strip(";"))
                elif line.startswith("blur"):
                    if "strength" in line:
                        self.settings["blur-strength"] = int(line.split("=")[1].strip().strip(";"))
                elif line.startswith("shadow-radius"):
                    self.settings["shadow-radius"] = int(line.split("=")[1].strip().strip(";"))
                elif line.startswith("shadow-opacity"):
                    self.settings["shadow-opacity"] = float(line.split("=")[1].strip().strip(";"))
                elif line.startswith("shadow"):
                    self.settings["shadow"] = line.split("=")[1].strip().strip(";").lower() == "true"
                elif line.startswith("fading"):
                    self.settings["fading"] = line.split("=")[1].strip().strip(";").lower() == "true"

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Example controls
        layout.addWidget(QLabel("Backend:"))
        self.backend_label = QLabel(self.settings["backend"])
        layout.addWidget(self.backend_label)

        layout.addWidget(QLabel("VSync:"))
        self.vsync_checkbox = QCheckBox()
        self.vsync_checkbox.setChecked(self.settings["vsync"])
        layout.addWidget(self.vsync_checkbox)

        layout.addWidget(QLabel("Inactive opacity:"))
        self.inactive_slider = QSlider(Qt.Orientation.Horizontal)
        self.inactive_slider.setMinimum(0)
        self.inactive_slider.setMaximum(100)
        self.inactive_slider.setValue(int(self.settings["inactive-opacity"] * 100))
        layout.addWidget(self.inactive_slider)

        layout.addWidget(QLabel("Active opacity:"))
        self.active_slider = QSlider(Qt.Orientation.Horizontal)
        self.active_slider.setMinimum(0)
        self.active_slider.setMaximum(100)
        self.active_slider.setValue(int(self.settings["active-opacity"] * 100))
        layout.addWidget(self.active_slider)

        # Save button
        self.save_btn = QPushButton("Save Config")
        self.save_btn.clicked.connect(self.save_config)
        layout.addWidget(self.save_btn)

    def save_config(self):
        if not self.config:
            # create a new file if missing
            self.config = ConfigFile(PICOM_PATH)
        # update only the lines we changed
        self._set_line("backend", f'backend = "{self.settings["backend"]}";')
        self._set_line("vsync", f'vsync = {"true" if self.vsync_checkbox.isChecked() else "false"};')
        self._set_line("inactive-opacity", f'inactive-opacity = {self.inactive_slider.value()/100:.2f};')
        self._set_line("active-opacity", f'active-opacity = {self.active_slider.value()/100:.2f};')
        # Save with backup
        bak = self.config.save(backup=True)
        print(f"Config saved! Backup: {bak}")

    def _set_line(self, key, new_line):
        """Replace the line starting with key, or append if missing."""
        found = False
        for idx, line in enumerate(self.config.lines):
            if line.strip().startswith(key):
                self.config.replace_line(idx, new_line)
                found = True
                break
        if not found:
            self.config.append_line(new_line)
