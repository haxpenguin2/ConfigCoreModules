import os
import shutil
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QLineEdit, QCheckBox, QPushButton, QApplication
)
from PyQt6.QtCore import Qt

class EditorWidget(QWidget):
    def __init__(self, config=None):
        super().__init__()
        self.config = config
        self.bashrc_path = os.path.expanduser("~/.bashrc")
        self.lines = []
        self.editable_widgets = {}
        self.load_bashrc()
        self.init_ui()

    def load_bashrc(self):
        if os.path.exists(self.bashrc_path):
            with open(self.bashrc_path, "r") as f:
                self.lines = f.readlines()
        else:
            self.lines = []

    def init_ui(self):
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        for i, line in enumerate(self.lines):
            line_strip = line.strip()
            if line_strip.startswith("# GUI_EDIT:"):
                key = line_strip.split(":")[1].strip()
                next_line = self.lines[i + 1].strip() if i + 1 < len(self.lines) else ""
                widget = self.create_widget(key, next_line)
                if widget:
                    self.layout.addLayout(widget)
                    self.editable_widgets[i + 1] = widget  # store line index

        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(self.save_changes)
        self.layout.addWidget(save_btn)

    def create_widget(self, key, value_line):
        layout = QHBoxLayout()
        layout.addWidget(QLabel(key))

        # Numeric slider
        if "=" in value_line and value_line.split("=")[1].isdigit():
            val = int(value_line.split("=")[1])
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(val*10 if val < 100 else val*2)
            slider.setValue(val)
            layout.addWidget(slider)
            return layout

        # Boolean toggle
        elif value_line.startswith("set -o"):
            cb = QCheckBox()
            cb.setChecked("on" in value_line or "true" in value_line)
            layout.addWidget(cb)
            return layout

        # Text line (aliases, PS1, etc)
        else:
            text_edit = QLineEdit(value_line)
            layout.addWidget(text_edit)
            return layout

    def save_changes(self):
        # Backup
        shutil.copy(self.bashrc_path, self.bashrc_path + ".bak")

        for index, layout in self.editable_widgets.items():
            widget = layout.itemAt(1).widget()
            if isinstance(widget, QSlider):
                new_val = widget.value()
                key = self.lines[index-1].strip().split(":")[1].strip()
                self.lines[index] = f"{key}={new_val}\n"
            elif isinstance(widget, QCheckBox):
                key = self.lines[index-1].strip().split(":")[1].strip()
                state = "on" if widget.isChecked() else "off"
                self.lines[index] = f"set -o {key} {state}\n"
            elif isinstance(widget, QLineEdit):
                self.lines[index] = widget.text() + "\n"

        with open(self.bashrc_path, "w") as f:
            f.writelines(self.lines)
        print("Bashrc saved successfully!")

# For testing standalone
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    w = EditorWidget()
    w.show()
    sys.exit(app.exec())
