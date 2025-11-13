#!/usr/bin/env python3
"""
Picom Editor plugin for ConfigCore
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSlider, QHBoxLayout, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt

# expects the core to pass a ConfigFile object
class EditorWidget(QWidget):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.setStyleSheet("""
            QWidget { background: #071018; color: #dbe7f5; font-family: 'Segoe UI', Roboto, sans-serif; }
            QSlider::handle:horizontal { background: #5c5cff; border-radius: 8px; }
            QSlider::groove:horizontal { height: 10px; background: #444; border-radius: 5px; }
            QPushButton { background-color: #5c5cff; border-radius: 5px; padding: 5px; color: #e6eef8; }
            QPushButton:hover { background-color: #4545ff; }
        """)
        self.picom_path = "~/.config/picom.conf"
        self.config = config
        self.load_config()
        self.init_ui()

    def load_config(self):
        try:
            import os
            from config_core import ConfigFile
            self.cf = ConfigFile(os.path.expanduser(self.picom_path))
        except Exception as e:
            QMessageBox.warning(self, "Load failed", f"Failed to load Picom config: {e}")
            self.cf = None
        self.settings = {}
        if self.cf:
            for line in self.cf.lines:
                if "=" in line and not line.strip().startswith("#"):
                    key, val = line.split("=", 1)
                    self.settings[key.strip()] = val.strip()

    def init_ui(self):
        layout = QVBoxLayout()
        self.sliders = {}

        # define the settings we want sliders for
        slider_defs = [
            ("blur-radius", 0, 50),
            ("shadow-radius", 0, 50),
            ("corner-radius", 0, 50),
            ("fading", 0, 1000),
            ("inactive-opacity", 0, 100)
        ]

        for key, mn, mx in slider_defs:
            val = int(float(self.settings.get(key, mn)))
            sld = self.create_slider(key, mn, mx, val)
            layout.addLayout(sld)
        save_btn = QPushButton("Save Picom Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)
        self.setLayout(layout)

    def create_slider(self, key, min_val, max_val, init_val):
        layout = QHBoxLayout()
        lbl = QLabel(key)
        sld = QSlider(Qt.Orientation.Horizontal)
        sld.setRange(min_val, max_val)
        sld.setValue(init_val)
        sld.valueChanged.connect(lambda v, k=key: self.on_slider_change(k, v))
        layout.addWidget(lbl)
        layout.addWidget(sld)
        self.sliders[key] = sld
        return layout

    def on_slider_change(self, key, value):
        self.settings[key] = str(value)

    def save_config(self):
        if not self.cf:
            QMessageBox.warning(self, "No config", "Cannot save: Picom config not loaded")
            return
        # update ConfigFile lines
        new_lines = []
        keys_handled = set()
        for line in self.cf.lines:
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                k, v = stripped.split("=", 1)
                k = k.strip()
                if k in self.settings:
                    new_lines.append(f"{k} = {self.settings[k]}")
                    keys_handled.add(k)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        # append any missing keys
        for k, v in self.settings.items():
            if k not in keys_handled:
                new_lines.append(f"{k} = {v}")
        self.cf.lines = new_lines
        self.cf.save()
        QMessageBox.information(self, "Saved", "Picom config saved successfully!")

# optional: factory function for core
def create_editor(config):
    return EditorWidget(config)
