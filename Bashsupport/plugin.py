import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider, QPushButton, QCheckBox
from PyQt5.QtCore import Qt

class EditorWidget(QWidget):
    def __init__(self, config=None):
        super().__init__()

        # path to ~/.bashrc
        self.config_path = os.path.expanduser("~/.bashrc")
        self.lines = []
        self._load_config()

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self._widgets = {}
        self._init_ui()

    # Load existing .bashrc lines
    def _load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                self.lines = f.readlines()
        else:
            self.lines = []

    # Build the UI
    def _init_ui(self):
        # Prompt brightness slider
        self.layout.addWidget(QLabel("Prompt brightness (0-100)"))
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(100)
        slider.setValue(self._get_ps1_brightness())
        self._widgets['prompt_brightness'] = slider
        self.layout.addWidget(slider)

        # ls alias checkbox
        checkbox = QCheckBox("Enable 'ls' color aliases")
        checkbox.setChecked(self._get_ls_alias())
        self._widgets['ls_alias'] = checkbox
        self.layout.addWidget(checkbox)

        # Save button
        save_btn = QPushButton("Save .bashrc")
        save_btn.clicked.connect(self.save_config)
        self.layout.addWidget(save_btn)

    # Get PS1_BRIGHTNESS from .bashrc
    def _get_ps1_brightness(self):
        for line in self.lines:
            if line.startswith("export PS1_BRIGHTNESS="):
                try:
                    return int(line.strip().split("=")[1])
                except:
                    return 50
        return 50

    # Check if ls alias is present
    def _get_ls_alias(self):
        for line in self.lines:
            if line.startswith("alias ls="):
                return True
        return False

    # Save changes to .bashrc
    def save_config(self):
        new_lines = []
        brightness_set = False
        ls_set = False

        for line in self.lines:
            if line.startswith("export PS1_BRIGHTNESS="):
                new_lines.append(f"export PS1_BRIGHTNESS={self._widgets['prompt_brightness'].value()}\n")
                brightness_set = True
            elif line.startswith("alias ls="):
                if self._widgets['ls_alias'].isChecked():
                    new_lines.append(line)
                ls_set = True
            else:
                new_lines.append(line)

        # Add missing lines if not present
        if not brightness_set:
            new_lines.append(f"\nexport PS1_BRIGHTNESS={self._widgets['prompt_brightness'].value()}\n")
        if self._widgets['ls_alias'].isChecked() and not ls_set:
            new_lines.append("\nalias ls='ls --color=auto'\n")

        # Write safely
        with open(self.config_path, "w") as f:
            f.writelines(new_lines)

        print(".bashrc updated successfully!")
