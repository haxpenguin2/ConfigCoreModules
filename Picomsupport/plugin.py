#!/usr/bin/env python3
"""
Picom Editor plugin for ConfigCore
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSlider, QHBoxLayout, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt
from pathlib import Path

class EditorWidget(QWidget):
    def __init__(self, config=None):
        super().__init__()

        # If core passes a ConfigFile, use it; else create one for Picom
        if config:
            self.cf = config
        else:
            from pathlib import Path
            picom_path = Path.home() / ".config/picom.conf"
            try:
                from config_core import ConfigFile
                self.cf = ConfigFile(str(picom_path))
            except Exception:
                self.cf = None

        # Default settings
        self.settings = {}
        if self.cf:
            for line in self.cf.lines:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    self.settings[k.strip()] = v.strip()

        # Dark modern style
        self.setStyleSheet("""
            QWidget { background: #071018; color: #dbe7f5; font-family: 'Segoe UI', Roboto, sans-serif; }
            QLabel { font-size: 12pt; }
            QSlider::handle:horizontal { background: #5c5cff; border-radius: 8px; width: 16px; }
            QSlider::groove:horizontal { height: 10px; background: #444; border-radius: 5px; }
            QPushButton { background-color: #5c5cff; border-radius: 5px; padding: 5px; color: #e6eef8; }
            QPushButton:hover { background-color: #4545ff; }
        """)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Define sliders
        slider_defs = [
            ("blur-radius", 0, 50),
            ("shadow-radius", 0, 50),
            ("corner-radius", 0, 50),
            ("fading", 0, 1000),
            ("inactive-opacity", 0, 100)
        ]
        self.sliders = {}
        for key, mn, mx in slider_defs:
            val = int(float(self.settings.get(key, mn)))
            layout.addLayout(self.create_slider(key, mn, mx, val))

        # Save button
        save_btn = QPushButton("Save Picom Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)

        self.setLayout(layout)

    def create_slider(self, key, min_val, max_val, init_val):
        layout = QHBoxLayout()
        lbl = QLabel(f"{key}: {init_val}")
        sld = QSlider(Qt.Orientation.Horizontal)
        sld.setRange(min_val, max_val)
        sld.setValue(init_val)
        sld.valueChanged.connect(lambda v, k=key, l=lbl: self.on_slider_change(k, v, l))
        layout.addWidget(lbl)
        layout.addWidget(sld)
        self.sliders[key] = sld
        return layout

    def on_slider_change(self, key, value, label):
        self.settings[key] = str(value)
        label.setText(f"{key}: {value}")

    def save_config(self):
        if not self.cf:
            QMessageBox.warning(self, "Error", "Picom config not loaded")
            return
        new_lines = []
        keys_handled = set()
        for line in self.cf.lines:
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                k, _ = stripped.split("=", 1)
                k = k.strip()
                if k in self.settings:
                    new_lines.append(f"{k} = {self.settings[k]}")
                    keys_handled.add(k)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        for k, v in self.settings.items():
            if k not in keys_handled:
                new_lines.append(f"{k} = {v}")
        self.cf.lines = new_lines
        self.cf.save()
        QMessageBox.information(self, "Saved", "Picom config saved!")

def create_editor(config=None):
    return EditorWidget(config)
