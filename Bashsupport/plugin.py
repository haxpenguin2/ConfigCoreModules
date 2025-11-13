import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider, QPushButton, QCheckBox, QHBoxLayout

class EditorWidget(QWidget):
    def __init__(self, config_path=None):
        super().__init__()

        self.config_path = os.path.expanduser("~/.bashrc")
        self.lines = []
        self._load_config()

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self._widgets = {}
        self.init_ui()

    def _load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                self.lines = f.readlines()
        else:
            self.lines = []

    def init_ui(self):
        # Example 1: PS1 prompt color brightness (0-100)
        self.layout.addWidget(QLabel("Prompt brightness (0-100)"))
        self._widgets['prompt_brightness'] = QSlider()
        self._widgets['prompt_brightness'].setMinimum(0)
        self._widgets['prompt_brightness'].setMaximum(100)
        self._widgets['prompt_brightness'].setValue(self._get_ps1_brightness())
        self.layout.addWidget(self._widgets['prompt_brightness'])

        # Example 2: Enable 'ls' aliases
        self._widgets['ls_alias'] = QCheckBox("Enable 'ls' color aliases")
        self._widgets['ls_alias'].setChecked(self._get_ls_alias())
        self.layout.addWidget(self._widgets['ls_alias'])

        # Save button
        save_btn = QPushButton("Save .bashrc")
        save_btn.clicked.connect(self.save_config)
        self.layout.addWidget(save_btn)

    # --- Helpers to parse current .bashrc ---
    def _get_ps1_brightness(self):
        for line in self.lines:
            if line.startswith("export PS1_BRIGHTNESS="):
                try:
                    return int(line.strip().split("=")[1])
                except:
                    return 50
        return 50

    def _get_ls_alias(self):
        for line in self.lines:
            if line.startswith("alias ls="):
                return True
        return False

    # --- Save changes ---
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

        # If not present, add new entries
        if not brightness_set:
            new_lines.append(f"\nexport PS1_BRIGHTNESS={self._widgets['prompt_brightness'].value()}\n")
        if self._widgets['ls_alias'].isChecked() and not ls_set:
            new_lines.append("\nalias ls='ls --color=auto'\n")

        # Write back safely
        with open(self.config_path, "w") as f:
            f.writelines(new_lines)

        print(".bashrc updated successfully!")
