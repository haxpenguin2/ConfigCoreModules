import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QSlider, QPushButton,
    QHBoxLayout, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt

class PicomEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Picom Config Editor")
        self.setMinimumSize(500, 400)
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e2f;
                color: #f0f0f0;
                font-family: Arial;
            }
            QSlider::handle:horizontal {
                background: #5c5cff;
                border-radius: 8px;
            }
            QSlider::groove:horizontal {
                height: 10px;
                background: #444;
                border-radius: 5px;
            }
            QPushButton {
                background-color: #5c5cff;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #4545ff;
            }
        """)
        self.config_path = os.path.expanduser("~/.config/picom.conf")
        self.config_data = {}

        self.load_config()
        self.init_ui()

    def load_config(self):
        if not os.path.isfile(self.config_path):
            QMessageBox.warning(self, "Picom config not found",
                                f"Could not find Picom config at {self.config_path}.")
            return
        with open(self.config_path, "r") as f:
            lines = f.readlines()
        # Simple parser: expects lines like `blur-background = true` or `shadow-radius = 10`
        self.config_data = {}
        for line in lines:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                self.config_data[key.strip()] = value.strip()

    def save_config(self):
        if not self.config_path:
            return
        with open(self.config_path, "w") as f:
            for key, value in self.config_data.items():
                f.write(f"{key} = {value}\n")
        QMessageBox.information(self, "Saved", "Picom config saved successfully!")

    def init_ui(self):
        layout = QVBoxLayout()

        # Blur slider
        self.blur_slider = self.create_slider("Blur radius", "blur-radius", 0, 50)
        layout.addLayout(self.blur_slider)

        # Shadow slider
        self.shadow_slider = self.create_slider("Shadow radius", "shadow-radius", 0, 50)
        layout.addLayout(self.shadow_slider)

        # Rounded corners slider
        self.rounded_slider = self.create_slider("Corner radius", "corner-radius", 0, 50)
        layout.addLayout(self.rounded_slider)

        # Fade transitions slider
        self.fade_slider = self.create_slider("Fade duration", "fading", 0, 1000)
        layout.addLayout(self.fade_slider)

        # Transparency slider
        self.transparency_slider = self.create_slider("Inactive opacity", "inactive-opacity", 0, 100)
        layout.addLayout(self.transparency_slider)

        # Save button
        save_btn = QPushButton("Save Config")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)

        self.setLayout(layout)

    def create_slider(self, label_text, key, min_val, max_val):
        layout = QHBoxLayout()
        label = QLabel(label_text)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        if key in self.config_data:
            try:
                slider.setValue(int(float(self.config_data[key])))
            except ValueError:
                slider.setValue(min_val)
        slider.valueChanged.connect(lambda val, k=key: self.update_config(k, val))
        layout.addWidget(label)
        layout.addWidget(slider)
        return layout

    def update_config(self, key, value):
        self.config_data[key] = str(value)


if __name__ == "__main__":
    app = QApplication([])
    editor = PicomEditor()
    editor.show()
    app.exec()
