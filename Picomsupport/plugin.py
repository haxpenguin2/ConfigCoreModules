# plugin.py — Picom editor plugin for your existing GUI core

import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox
)
from PyQt6.QtCore import Qt

# Add your core folder to sys.path so ConfigFile can be imported
sys.path.append(os.path.expanduser("~/.config_editor_packages/"))
try:
    from config_core import ConfigFile
except ImportError:
    ConfigFile = None  # will handle missing core

class EditorWidget(QWidget):
    def __init__(self, config: ConfigFile):
        super().__init__()
        self.config = config
        self.picom_path = Path.home() / ".config" / "picom.conf"
        self.settings = {
            "backend": "glx",
            "vsync": True,
            "corner-radius": 10,
            "inactive-opacity": 0.7,
            "active-opacity": 1.0,
            "frame-opacity": 1.0,
            "fade-in-step": 0.03,
            "fade-out-step": 0.03,
            "fade-delta": 10,
            "fading": True,
            "blur-strength": 5,
            "shadow": True,
            "shadow-radius": 12
        }

        self.load_config()
        self.init_ui()

    # -------------------------
    # Load config values safely
    # -------------------------
    def load_config(self):
        if not self.picom_path.exists():
            return
        with open(self.picom_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or line == "":
                    continue
                # simple parsing for basic types
                for key in self.settings.keys():
                    if line.startswith(f"{key} ="):
                        val = line.split("=", 1)[1].strip().rstrip(";")
                        if val.lower() in ("true", "false"):
                            self.settings[key] = val.lower() == "true"
                        else:
                            try:
                                if "." in val:
                                    self.settings[key] = float(val)
                                else:
                                    self.settings[key] = int(val)
                            except ValueError:
                                self.settings[key] = val.strip('"')

    # -------------------------
    # Build GUI
    # -------------------------
    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Show current file
        layout.addWidget(QLabel(f"Editing Picom config: {self.picom_path}"))

        # Opacity settings
        self.inactive_opacity_spin = QDoubleSpinBox()
        self.inactive_opacity_spin.setRange(0.0, 1.0)
        self.inactive_opacity_spin.setSingleStep(0.05)
        self.inactive_opacity_spin.setValue(self.settings["inactive-opacity"])
        layout.addLayout(self._row("Inactive window opacity:", self.inactive_opacity_spin))

        self.active_opacity_spin = QDoubleSpinBox()
        self.active_opacity_spin.setRange(0.0, 1.0)
        self.active_opacity_spin.setSingleStep(0.05)
        self.active_opacity_spin.setValue(self.settings["active-opacity"])
        layout.addLayout(self._row("Active window opacity:", self.active_opacity_spin))

        # Fade steps
        self.fade_in_spin = QDoubleSpinBox()
        self.fade_in_spin.setRange(0.001, 1.0)
        self.fade_in_spin.setSingleStep(0.01)
        self.fade_in_spin.setValue(self.settings["fade-in-step"])
        layout.addLayout(self._row("Fade in step:", self.fade_in_spin))

        self.fade_out_spin = QDoubleSpinBox()
        self.fade_out_spin.setRange(0.001, 1.0)
        self.fade_out_spin.setSingleStep(0.01)
        self.fade_out_spin.setValue(self.settings["fade-out-step"])
        layout.addLayout(self._row("Fade out step:", self.fade_out_spin))

        # Rounded corners
        self.corner_spin = QSpinBox()
        self.corner_spin.setRange(0, 50)
        self.corner_spin.setValue(self.settings["corner-radius"])
        layout.addLayout(self._row("Corner radius:", self.corner_spin))

        # Blur
        self.blur_spin = QSpinBox()
        self.blur_spin.setRange(0, 20)
        self.blur_spin.setValue(self.settings["blur-strength"])
        layout.addLayout(self._row("Blur strength:", self.blur_spin))

        # Shadow
        self.shadow_check = QCheckBox("Enable shadow")
        self.shadow_check.setChecked(self.settings["shadow"])
        layout.addWidget(self.shadow_check)

        self.shadow_radius_spin = QSpinBox()
        self.shadow_radius_spin.setRange(0, 50)
        self.shadow_radius_spin.setValue(self.settings["shadow-radius"])
        layout.addLayout(self._row("Shadow radius:", self.shadow_radius_spin))

        # Save button
        save_btn = QPushButton("Save Picom Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)

        layout.addStretch()

    def _row(self, label_text, widget):
        row = QHBoxLayout()
        row.addWidget(QLabel(label_text))
        row.addWidget(widget)
        return row

    # -------------------------
    # Save changes (only modified lines)
    # -------------------------
    def save_config(self):
        if not self.picom_path.exists():
            self.picom_path.parent.mkdir(parents=True, exist_ok=True)
            self.picom_path.touch()
        lines = self.picom_path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        keys_to_write = {
            "inactive-opacity": self.inactive_opacity_spin.value(),
            "active-opacity": self.active_opacity_spin.value(),
            "fade-in-step": self.fade_in_spin.value(),
            "fade-out-step": self.fade_out_spin.value(),
            "corner-radius": self.corner_spin.value(),
            "blur-strength": self.blur_spin.value(),
            "shadow": self.shadow_check.isChecked(),
            "shadow-radius": self.shadow_radius_spin.value()
        }

        # update only existing lines or append if missing
        keys_written = set()
        for line in lines:
            stripped = line.strip()
            updated = False
            for key, val in keys_to_write.items():
                if stripped.startswith(f"{key} ="):
                    if isinstance(val, bool):
                        new_val = "true" if val else "false"
                    elif isinstance(val, str):
                        new_val = f'"{val}"'
                    else:
                        new_val = str(val)
                    new_lines.append(f"{key} = {new_val};")
                    keys_written.add(key)
                    updated = True
                    break
            if not updated:
                new_lines.append(line)
        # append any missing keys
        for key, val in keys_to_write.items():
            if key not in keys_written:
                if isinstance(val, bool):
                    new_val = "true" if val else "false"
                elif isinstance(val, str):
                    new_val = f'"{val}"'
                else:
                    new_val = str(val)
                new_lines.append(f"{key} = {new_val};")

        self.picom_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print(f"Saved Picom config to {self.picom_path}")
