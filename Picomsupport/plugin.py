# ~/.config_editor_packages/Picomsupport/plugin.py

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QMessageBox, QLineEdit
)
from PyQt6.QtCore import Qt

class EditorWidget(QWidget):
    def __init__(self, config):
        """
        `config` is a ConfigFile object passed from CoreGUI
        """
        super().__init__()
        self.config = config
        self.init_ui()

    # ---------------------------
    # Config parsing helpers
    # ---------------------------
    def _find_key_line(self, key):
        """
        Returns the index of the line where `key` is set.
        Returns None if not found.
        """
        for i, line in enumerate(self.config.lines):
            if line.strip().startswith(f"{key}"):
                return i
        return None

    def get_value(self, key, default=None):
        idx = self._find_key_line(key)
        if idx is None:
            return default
        line = self.config.lines[idx]
        # remove key, =, ;, whitespace
        val = line.split("=", 1)[-1].strip().rstrip(";")
        # convert bools
        if val.lower() == "true":
            return True
        elif val.lower() == "false":
            return False
        try:
            return float(val)
        except Exception:
            return val.strip('"')

    def set_value(self, key, value):
        idx = self._find_key_line(key)
        line_value = f"{key} = {str(value).lower()};" if isinstance(value, bool) else f'{key} = {value};'
        if idx is not None:
            lw = self.config.lines[idx][:len(self.config.lines[idx]) - len(self.config.lines[idx].lstrip())]
            self.config.lines[idx] = lw + line_value
        else:
            self.config.append_line(line_value)

    # ---------------------------
    # Blur block helpers
    # ---------------------------
    def get_blur_strength(self):
        in_block = False
        for line in self.config.lines:
            stripped = line.strip()
            if stripped.startswith("blur") and "{" in stripped:
                in_block = True
            elif in_block:
                if stripped.startswith("strength"):
                    val = stripped.split("=")[-1].strip().rstrip(";")
                    try:
                        return int(val)
                    except:
                        return 5
                elif stripped.startswith("};"):
                    break
        return 5

    def set_blur_strength(self, val):
        in_block = False
        for i, line in enumerate(self.config.lines):
            stripped = line.strip()
            if stripped.startswith("blur") and "{" in stripped:
                in_block = True
            elif in_block:
                if stripped.startswith("strength"):
                    lw = line[:len(line) - len(line.lstrip())]
                    self.config.lines[i] = f"{lw}strength = {val};"
                    return

    # ---------------------------
    # UI
    # ---------------------------
    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Opacity sliders
        self.inactive_opacity_slider = self._create_slider("inactive-opacity", 0.0, 1.0, 0.01)
        layout.addLayout(self.inactive_opacity_slider)

        self.active_opacity_slider = self._create_slider("active-opacity", 0.0, 1.0, 0.01)
        layout.addLayout(self.active_opacity_slider)

        # Blur strength
        blur_label = QLabel("Blur strength")
        layout.addWidget(blur_label)
        self.blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_slider.setMinimum(0)
        self.blur_slider.setMaximum(20)
        self.blur_slider.setValue(self.get_blur_strength())
        self.blur_slider.valueChanged.connect(self._on_blur_change)
        layout.addWidget(self.blur_slider)

        # Corner radius
        self.corner_slider = self._create_slider("corner-radius", 0, 50, 1)
        layout.addLayout(self.corner_slider)

        # Fade step
        self.fade_in_slider = self._create_slider("fade-in-step", 0.0, 0.1, 0.01)
        layout.addLayout(self.fade_in_slider)

        self.fade_out_slider = self._create_slider("fade-out-step", 0.0, 0.1, 0.01)
        layout.addLayout(self.fade_out_slider)

        # Save button
        save_btn = QPushButton("Save Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)

    # ---------------------------
    # Slider helpers
    # ---------------------------
    def _create_slider(self, key, min_val, max_val, step):
        layout = QHBoxLayout()
        label = QLabel(f"{key}: {self.get_value(key, 0)}")
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(int(min_val / step))
        slider.setMaximum(int(max_val / step))
        slider.setValue(int(self.get_value(key, 0) / step))
        slider.valueChanged.connect(lambda v, k=key, s=slider, st=step, l=label: self._on_slider_change(k, v, s, st, l))
        layout.addWidget(label)
        layout.addWidget(slider)
        return layout

    def _on_slider_change(self, key, value, slider, step, label):
        real_val = value * step
        self.set_value(key, real_val)
        label.setText(f"{key}: {real_val}")

    def _on_blur_change(self, value):
        self.set_blur_strength(value)

    # ---------------------------
    # Save
    # ---------------------------
    def save_config(self):
        backup = self.config.save(backup=True)
        QMessageBox.information(self, "Saved", f"Config saved!\nBackup: {backup}")
