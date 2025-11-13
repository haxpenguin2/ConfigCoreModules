# plugin.py
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QPushButton, QCheckBox, QComboBox
)
from PyQt5.QtCore import Qt
from pathlib import Path
import shutil

# ===== PicomConfig parser class =====
class PicomConfig:
    """
    Simple Picom config parser to safely edit and save keys,
    preserving comments and unknown lines.
    """
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.lines = []
        self.key_map = {}  # key -> (line_index, line_content)
        self.load()

    def load(self):
        if not self.filepath.exists():
            self.lines = []
            return
        self.lines = self.filepath.read_text().splitlines()
        for i, line in enumerate(self.lines):
            line_strip = line.strip()
            if not line_strip or line_strip.startswith("#"):
                continue
            if "=" in line_strip:
                key, value = line_strip.split("=", 1)
                self.key_map[key.strip()] = (i, value.strip().rstrip(";"))

    def get_value(self, key, default=None):
        item = self.key_map.get(key)
        if item:
            _, val = item
            try:
                # try converting to float or int
                if "." in val:
                    return float(val)
                if val.lower() in ["true", "false"]:
                    return val.lower() == "true"
                return int(val)
            except:
                return val.strip('"')
        return default

    def set_value(self, key, value):
        val_str = ""
        if isinstance(value, bool):
            val_str = "true" if value else "false"
        elif isinstance(value, (int, float)):
            val_str = str(value)
        else:
            val_str = f'"{value}"'
        val_str += ";"

        if key in self.key_map:
            i, _ = self.key_map[key]
            self.lines[i] = f"{key} = {val_str}"
            self.key_map[key] = (i, val_str)
        else:
            self.lines.append(f"{key} = {val_str}")
            self.key_map[key] = (len(self.lines)-1, val_str)

    def save(self):
        # make backup
        backup = self.filepath.with_suffix(".conf.bak")
        if self.filepath.exists():
            shutil.copy(self.filepath, backup)
        self.filepath.write_text("\n".join(self.lines))
        print(f"Saved config with backup at {backup}")


# ===== Picom Editor GUI Plugin =====
class EditorWidget(QWidget):
    def __init__(self, config_path):
        super().__init__()
        self.config_path = Path(config_path)
        self.config = PicomConfig(str(self.config_path))
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # ===== Backend dropdown =====
        layout.addWidget(QLabel("Backend"))
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["xrender", "glx", "xr_glx_hybrid"])
        self.backend_combo.setCurrentText(self.config.get_value("backend", "glx"))
        self.backend_combo.currentTextChanged.connect(
            lambda v: self.config.set_value("backend", v)
        )
        layout.addWidget(self.backend_combo)

        # ===== Vsync checkbox =====
        self.vsync_cb = QCheckBox("Enable Vsync")
        self.vsync_cb.setChecked(self.config.get_value("vsync", True))
        self.vsync_cb.stateChanged.connect(
            lambda state: self.config.set_value("vsync", state==Qt.Checked)
        )
        layout.addWidget(self.vsync_cb)

        # ===== Rounded corners =====
        self.round_cb = QCheckBox("Rounded corners")
        self.round_cb.setChecked(self.config.get_value("rounded-corners", True))
        self.round_cb.stateChanged.connect(
            lambda state: self.config.set_value("rounded-corners", state==Qt.Checked)
        )
        layout.addWidget(self.round_cb)

        self.corner_slider_label = QLabel(f"Corner radius: {self.config.get_value('corner-radius',10)}")
        layout.addWidget(self.corner_slider_label)
        self.corner_slider = QSlider(Qt.Horizontal)
        self.corner_slider.setRange(0,50)
        self.corner_slider.setValue(int(self.config.get_value("corner-radius",10)))
        self.corner_slider.valueChanged.connect(self.update_corner_radius)
        layout.addWidget(self.corner_slider)

        # ===== Opacity =====
        layout.addWidget(QLabel("Inactive window opacity"))
        self.inactive_slider = QSlider(Qt.Horizontal)
        self.inactive_slider.setRange(0,100)
        self.inactive_slider.setValue(int(self.config.get_value("inactive-opacity",0.7)*100))
        self.inactive_label = QLabel(f"{self.config.get_value('inactive-opacity',0.7):.2f}")
        self.inactive_slider.valueChanged.connect(self.update_inactive_opacity)
        layout.addWidget(self.inactive_slider)
        layout.addWidget(self.inactive_label)

        layout.addWidget(QLabel("Active window opacity"))
        self.active_slider = QSlider(Qt.Horizontal)
        self.active_slider.setRange(0,100)
        self.active_slider.setValue(int(self.config.get_value("active-opacity",1.0)*100))
        self.active_label = QLabel(f"{self.config.get_value('active-opacity',1.0):.2f}")
        self.active_slider.valueChanged.connect(self.update_active_opacity)
        layout.addWidget(self.active_slider)
        layout.addWidget(self.active_label)

        # ===== Fading =====
        self.fading_cb = QCheckBox("Enable Fading")
        self.fading_cb.setChecked(self.config.get_value("fading", True))
        self.fading_cb.stateChanged.connect(
            lambda state: self.config.set_value("fading", state==Qt.Checked)
        )
        layout.addWidget(self.fading_cb)

        self.fade_in_label = QLabel(f"Fade-in step: {self.config.get_value('fade-in-step',0.03):.2f}")
        layout.addWidget(self.fade_in_label)
        self.fade_in_slider = QSlider(Qt.Horizontal)
        self.fade_in_slider.setRange(1,100)
        self.fade_in_slider.setValue(int(self.config.get_value("fade-in-step",0.03)*100))
        self.fade_in_slider.valueChanged.connect(self.update_fade_in)
        layout.addWidget(self.fade_in_slider)

        # ===== Shadow settings =====
        self.shadow_cb = QCheckBox("Enable Shadow")
        self.shadow_cb.setChecked(self.config.get_value("shadow", True))
        self.shadow_cb.stateChanged.connect(lambda state: self.config.set_value("shadow", state==Qt.Checked))
        layout.addWidget(self.shadow_cb)

        self.shadow_radius_label = QLabel(f"Shadow radius: {self.config.get_value('shadow-radius',12)}")
        layout.addWidget(self.shadow_radius_label)
        self.shadow_radius_slider = QSlider(Qt.Horizontal)
        self.shadow_radius_slider.setRange(0,50)
        self.shadow_radius_slider.setValue(int(self.config.get_value("shadow-radius",12)))
        self.shadow_radius_slider.valueChanged.connect(self.update_shadow_radius)
        layout.addWidget(self.shadow_radius_slider)

        # ===== Blur =====
        layout.addWidget(QLabel("Blur strength"))
        self.blur_strength_slider = QSlider(Qt.Horizontal)
        self.blur_strength_slider.setRange(0,20)
        self.blur_strength_slider.setValue(int(self.config.get_value("strength",5)))
        self.blur_strength_slider.valueChanged.connect(self.update_blur_strength)
        layout.addWidget(self.blur_strength_slider)

        # ===== Save button =====
        save_btn = QPushButton("Save Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)

        self.setLayout(layout)

    # ===== Slider update methods =====
    def update_corner_radius(self, val):
        self.corner_slider_label.setText(f"Corner radius: {val}")
        self.config.set_value("corner-radius", val)

    def update_inactive_opacity(self, val):
        v = val/100
        self.inactive_label.setText(f"{v:.2f}")
        self.config.set_value("inactive-opacity", v)

    def update_active_opacity(self, val):
        v = val/100
        self.active_label.setText(f"{v:.2f}")
        self.config.set_value("active-opacity", v)

    def update_fade_in(self, val):
        v = val/100
        self.fade_in_label.setText(f"Fade-in step: {v:.2f}")
        self.config.set_value("fade-in-step", v)

    def update_shadow_radius(self, val):
        self.shadow_radius_label.setText(f"Shadow radius: {val}")
        self.config.set_value("shadow-radius", val)

    def update_blur_strength(self, val):
        self.config.set_value("strength", val)

    # ===== Save config safely =====
    def save_config(self):
        try:
            self.config.save()
        except Exception as e:
            print("Error saving config:", e)
