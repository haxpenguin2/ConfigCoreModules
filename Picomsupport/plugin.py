# plugin.py
# Full-featured Picom Editor Plugin for CoreGUI
# Safe, lazy-loaded UI

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QDoubleSpinBox, QPushButton, QCheckBox, QComboBox
)

try:
    from config_core import ConfigFile
except ModuleNotFoundError:
    import sys, os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from config_core import ConfigFile

class EditorWidget(QWidget):
    def __init__(self, config_path):
        super().__init__()
        self.config_path = config_path
        self.config = ConfigFile(config_path)
        self._ui_initialized = False

    def _load_settings(self):
        cfg = self.config
        # Convert values safely
        def get_float(key, default):
            try: return float(cfg.get(key, default))
            except: return default
        def get_int(key, default):
            try: return int(cfg.get(key, default))
            except: return default
        def get_bool(key, default):
            return cfg.get(key, str(default)).lower() == "true"

        return {
            "backend": cfg.get("backend", "glx"),
            "vsync": get_bool("vsync", True),
            "inactive-opacity": get_float("inactive-opacity", 0.7),
            "active-opacity": get_float("active-opacity", 1.0),
            "frame-opacity": get_float("frame-opacity", 1.0),
            "shadow": get_bool("shadow", True),
            "shadow-radius": get_int("shadow-radius", 12),
            "shadow-opacity": get_float("shadow-opacity", 0.25),
            "corner-radius": get_int("corner-radius", 10),
            "rounded-corners": get_bool("rounded-corners", True),
            "fading": get_bool("fading", True),
            "fade-in-step": get_float("fade-in-step", 0.03),
            "fade-out-step": get_float("fade-out-step", 0.03),
            "fade-delta": get_int("fade-delta", 10),
        }

    def init_ui(self):
        if self._ui_initialized:
            return

        self.settings = self._load_settings()

        layout = QVBoxLayout()

        # Backend
        layout.addWidget(QLabel("Backend"))
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["xrender", "glx", "xr_glx_hybrid"])
        self.backend_combo.setCurrentText(self.settings["backend"])
        layout.addWidget(self.backend_combo)

        # VSync
        self.vsync_checkbox = QCheckBox("Enable VSync")
        self.vsync_checkbox.setChecked(self.settings["vsync"])
        layout.addWidget(self.vsync_checkbox)

        # Opacity
        for name, label_text in [("inactive-opacity", "Inactive Opacity"),
                                 ("active-opacity", "Active Opacity"),
                                 ("frame-opacity", "Frame Opacity")]:
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.01)
            spin.setValue(self.settings[name])
            setattr(self, f"{name.replace('-', '_')}_spin", spin)
            layout.addWidget(QLabel(label_text))
            layout.addWidget(spin)

        # Shadow settings
        self.shadow_checkbox = QCheckBox("Enable Shadows")
        self.shadow_checkbox.setChecked(self.settings["shadow"])
        layout.addWidget(self.shadow_checkbox)

        self.shadow_radius_spin = QDoubleSpinBox()
        self.shadow_radius_spin.setRange(0, 50)
        self.shadow_radius_spin.setValue(self.settings["shadow-radius"])
        layout.addWidget(QLabel("Shadow Radius"))
        layout.addWidget(self.shadow_radius_spin)

        self.shadow_opacity_spin = QDoubleSpinBox()
        self.shadow_opacity_spin.setRange(0.0, 1.0)
        self.shadow_opacity_spin.setSingleStep(0.01)
        self.shadow_opacity_spin.setValue(self.settings["shadow-opacity"])
        layout.addWidget(QLabel("Shadow Opacity"))
        layout.addWidget(self.shadow_opacity_spin)

        # Rounded corners
        self.rounded_checkbox = QCheckBox("Enable Rounded Corners")
        self.rounded_checkbox.setChecked(self.settings["rounded-corners"])
        layout.addWidget(self.rounded_checkbox)

        self.corner_radius_spin = QDoubleSpinBox()
        self.corner_radius_spin.setRange(0, 50)
        self.corner_radius_spin.setValue(self.settings["corner-radius"])
        layout.addWidget(QLabel("Corner Radius"))
        layout.addWidget(self.corner_radius_spin)

        # Fading
        self.fading_checkbox = QCheckBox("Enable Fading")
        self.fading_checkbox.setChecked(self.settings["fading"])
        layout.addWidget(self.fading_checkbox)

        self.fade_in_spin = QDoubleSpinBox()
        self.fade_in_spin.setRange(0.0, 1.0)
        self.fade_in_spin.setSingleStep(0.01)
        self.fade_in_spin.setValue(self.settings["fade-in-step"])
        layout.addWidget(QLabel("Fade In Step"))
        layout.addWidget(self.fade_in_spin)

        self.fade_out_spin = QDoubleSpinBox()
        self.fade_out_spin.setRange(0.0, 1.0)
        self.fade_out_spin.setSingleStep(0.01)
        self.fade_out_spin.setValue(self.settings["fade-out-step"])
        layout.addWidget(QLabel("Fade Out Step"))
        layout.addWidget(self.fade_out_spin)

        self.fade_delta_spin = QDoubleSpinBox()
        self.fade_delta_spin.setRange(0, 100)
        self.fade_delta_spin.setValue(self.settings["fade-delta"])
        layout.addWidget(QLabel("Fade Delta (ms)"))
        layout.addWidget(self.fade_delta_spin)

        # Save button
        self.save_btn = QPushButton("Save Config")
        self.save_btn.clicked.connect(self.save_config)
        layout.addWidget(self.save_btn)

        self.setLayout(layout)
        self._ui_initialized = True

    def save_config(self):
        self.config.set("backend", self.backend_combo.currentText())
        self.config.set("vsync", "true" if self.vsync_checkbox.isChecked() else "false")
        for name in ["inactive-opacity", "active-opacity", "frame-opacity"]:
            spin = getattr(self, f"{name.replace('-', '_')}_spin")
            self.config.set(name, str(spin.value()))
        self.config.set("shadow", "true" if self.shadow_checkbox.isChecked() else "false")
        self.config.set("shadow-radius", str(int(self.shadow_radius_spin.value())))
        self.config.set("shadow-opacity", str(self.shadow_opacity_spin.value()))
        self.config.set("rounded-corners", "true" if self.rounded_checkbox.isChecked() else "false")
        self.config.set("corner-radius", str(int(self.corner_radius_spin.value())))
        self.config.set("fading", "true" if self.fading_checkbox.isChecked() else "false")
        self.config.set("fade-in-step", str(self.fade_in_spin.value()))
        self.config.set("fade-out-step", str(self.fade_out_spin.value()))
        self.config.set("fade-delta", str(int(self.fade_delta_spin.value())))
        self.config.save()
