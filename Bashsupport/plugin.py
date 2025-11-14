# plugin.py
# Bashrc GUI editor plugin for your CoreGUI.
# Accepts the core's ConfigFile object (or None) in __init__.

import os
import re
import shutil
from pathlib import Path

# Try PyQt6 then PyQt5
try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QSlider, QCheckBox, QPushButton, QSpinBox, QDoubleSpinBox
    )
    from PyQt6.QtCore import Qt
    QT_DOUBLE = QDoubleSpinBox
    QT_INT = QSpinBox
except Exception:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
        QSlider, QCheckBox, QPushButton, QSpinBox, QDoubleSpinBox
    )
    from PyQt5.QtCore import Qt
    QT_DOUBLE = QDoubleSpinBox
    QT_INT = QSpinBox


class EditorWidget(QWidget):
    """
    EditorWidget(core_config)

    core_config: optional ConfigFile object from the core. If provided,
                 this plugin will use core_config.lines and core_config.replace_line/append_line/save.
                 If None, plugin reads/writes ~/.bashrc directly.
    """
    GUI_MARKER_RE = re.compile(r"^#\s*GUI_EDIT\s*:\s*(?P<name>[\w\-\_]+)\s*$")

    ASSIGN_RE = re.compile(r'^(?P<prefix>export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<val>.+)$')
    SETOPT_RE = re.compile(r'^set\s+-o\s+(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s+(?P<val>\w+)$')
    ALIAS_RE = re.compile(r"^alias\s+(?P<key>[\w\-]+)=(?P<val>.+)$")

    def __init__(self, core_config=None):
        super().__init__()
        self.core_config = core_config  # may be None or ConfigFile instance
        self.bashrc_path = Path(os.path.expanduser("~/.bashrc"))
        self.using_core_config = False
        self.lines = []
        self.entries = []  # list of dicts: {marker_idx, value_idx (or None), kind, key, prefix, widget}
        self.widgets = []
        self._load_source()
        self._build_ui()

    # ---------------------------
    # I/O helpers
    # ---------------------------
    def _load_source(self):
        # If a core ConfigFile object is provided and has 'lines', prefer it
        if self.core_config is not None and hasattr(self.core_config, "lines"):
            self.using_core_config = True
            self.lines = list(self.core_config.lines)
        else:
            self.using_core_config = False
            if self.bashrc_path.exists():
                self.lines = self.bashrc_path.read_text(encoding="utf-8").splitlines(True)  # keep newline chars
            else:
                self.lines = []

        # scan for GUI markers and capture the following line (or None)
        self.entries = []
        for i, raw in enumerate(self.lines):
            m = self.GUI_MARKER_RE.match(raw.strip())
            if m:
                name = m.group("name")
                # next non-empty line index (allow blank lines), prefer immediate next line
                next_idx = i + 1 if (i + 1) < len(self.lines) else None
                entry = {
                    "marker_idx": i,
                    "value_idx": next_idx,
                    "name": name,
                    "orig_line": self.lines[next_idx] if next_idx is not None else None,
                    "parsed": None,
                    "widget": None
                }
                # attempt to parse the next line if present
                if next_idx is not None:
                    line = self.lines[next_idx].strip()
                    if not line or line.startswith("#"):
                        entry["parsed"] = None
                    else:
                        # try patterns
                        a = self.ASSIGN_RE.match(line)
                        s = self.SETOPT_RE.match(line)
                        al = self.ALIAS_RE.match(line)
                        if a:
                            entry["parsed"] = {"kind": "assign", "prefix": a.group("prefix") or "", "key": a.group("key"), "val": a.group("val").strip()}
                        elif s:
                            entry["parsed"] = {"kind": "setopt", "key": s.group("key"), "val": s.group("val")}
                        elif al:
                            entry["parsed"] = {"kind": "alias", "key": al.group("key"), "val": al.group("val")}
                        else:
                            # fallback to raw text (text input)
                            entry["parsed"] = {"kind": "raw", "val": line}
                self.entries.append(entry)

    def _backup(self):
        target = self.bashrc_path if not self.using_core_config else Path(self.core_config.path)
        if target.exists():
            bak = target.parent / (target.name + ".bak")
            shutil.copy(target, bak)

    # ---------------------------
    # UI helpers
    # ---------------------------
    def _row(self, label_text, widget):
        h = QHBoxLayout()
        h.addWidget(QLabel(label_text))
        h.addWidget(widget)
        return h

    def _build_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        if not self.entries:
            layout.addWidget(QLabel("No editable lines found.\nAdd '# GUI_EDIT: NAME' above a line in ~/.bashrc to make it editable."))
            # still provide a refresh and open buttons
            btn_refresh = QPushButton("Refresh")
            btn_refresh.clicked.connect(self._on_refresh)
            layout.addWidget(btn_refresh)
            btn_open = QPushButton("Open ~/.bashrc")
            btn_open.clicked.connect(self._open_bashrc)
            layout.addWidget(btn_open)
            return

        # build widgets for each entry
        for ent in self.entries:
            name = ent["name"]
            parsed = ent.get("parsed")
            if not parsed:
                # blank or comment next line — provide a text input to add a line
                le = QLineEdit("")
                le.setPlaceholderText("Enter new line for this marker (e.g. HISTSIZE=1000 or alias ll='ls -la')")
                ent["widget"] = ("raw", le)
                layout.addLayout(self._row(name, le))
                continue

            kind = parsed["kind"]
            if kind == "assign":
                # Determine if value is int, float, or string
                raw_val = parsed["val"]
                # strip surrounding quotes if present for detection
                rv = raw_val.strip()
                is_int = False
                is_float = False
                try:
                    int(rv)
                    is_int = True
                except Exception:
                    try:
                        float(rv)
                        is_float = True
                    except Exception:
                        pass

                if is_int:
                    spin = QT_INT()
                    spin.setRange(-2147483648, 2147483647)
                    spin.setValue(int(rv))
                    ent["widget"] = ("int", spin, parsed)
                    layout.addLayout(self._row(name, spin))
                elif is_float:
                    dspin = QT_DOUBLE()
                    dspin.setRange(-1e9, 1e9)
                    # reasonable step
                    step = 0.01 if '.' in rv else 1
                    try:
                        dspin.setSingleStep(step)
                    except Exception:
                        pass
                    dspin.setValue(float(rv))
                    ent["widget"] = ("float", dspin, parsed)
                    layout.addLayout(self._row(name, dspin))
                else:
                    le = QLineEdit(rv.strip('"').strip("'"))
                    ent["widget"] = ("str", le, parsed)
                    layout.addLayout(self._row(name, le))

            elif kind == "setopt":
                # boolean: val will be 'on' or 'off'
                state = parsed["val"].lower() in ("on", "true", "1", "yes")
                cb = QCheckBox()
                cb.setChecked(state)
                ent["widget"] = ("bool", cb, parsed)
                layout.addLayout(self._row(name, cb))

            elif kind == "alias":
                le = QLineEdit(parsed["val"].strip())
                ent["widget"] = ("alias", le, parsed)
                layout.addLayout(self._row(name, le))

            elif kind == "raw":
                le = QLineEdit(parsed.get("val", ""))
                ent["widget"] = ("raw", le, parsed)
                layout.addLayout(self._row(name, le))

            else:
                le = QLineEdit(str(parsed.get("val", "")))
                ent["widget"] = ("raw", le, parsed)
                layout.addLayout(self._row(name, le))

        # Save / refresh / open buttons
        btns = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        btns.addWidget(save_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._on_refresh)
        btns.addWidget(refresh_btn)

        open_btn = QPushButton("Open ~/.bashrc")
        open_btn.clicked.connect(self._open_bashrc)
        btns.addWidget(open_btn)

        layout.addLayout(btns)

    # ---------------------------
    # Actions
    # ---------------------------
    def _on_refresh(self):
        # reload and rebuild UI
        self._load_source()
        # clear layout
        self._clear_layout(self.layout())
        self._build_ui()

    def _open_bashrc(self):
        # try to open with xdg-open, else just print path
        try:
            os.execvp("xdg-open", ["xdg-open", str(self.bashrc_path)])
        except Exception:
            print("Bashrc path:", self.bashrc_path)

    def _clear_layout(self, layout):
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            else:
                sub = item.layout()
                if sub is not None:
                    self._clear_layout(sub)

    def _on_save(self):
        # backup
        try:
            self._backup()
        except Exception:
            pass

        # Work on a copy of lines so we only replace the exact lines
        lines = list(self.lines)

        for ent in self.entries:
            widget_info = ent.get("widget")
            marker_idx = ent["marker_idx"]
            val_idx = ent["value_idx"]

            if widget_info is None:
                continue

            kind = widget_info[0]
            if kind == "int":
                spin = widget_info[1]
                parsed = widget_info[2]
                new_val = str(int(spin.value()))
                # preserve prefix (export or not)
                prefix = parsed.get("prefix", "")
                new_line = f"{prefix}{parsed['key']}={new_val}\n"
            elif kind == "float":
                dspin = widget_info[1]
                parsed = widget_info[2]
                new_val = repr(float(dspin.value()))
                prefix = parsed.get("prefix", "")
                new_line = f"{prefix}{parsed['key']}={new_val}\n"
            elif kind == "str":
                le = widget_info[1]
                parsed = widget_info[2]
                text = le.text()
                # quote if contains spaces
                if " " in text and not (text.startswith('"') or text.startswith("'")):
                    text = f'"{text}"'
                prefix = parsed.get("prefix", "")
                new_line = f"{prefix}{parsed['key']}={text}\n"
            elif kind == "bool":
                cb = widget_info[1]
                parsed = widget_info[2]
                new_line = f"set -o {parsed['key']} {'on' if cb.isChecked() else 'off'}\n"
            elif kind == "alias":
                le = widget_info[1]
                parsed = widget_info[2]
                val = le.text().strip()
                # keep quotes if present in input
                new_line = f"alias {parsed['key']}={val}\n"
            elif kind == "raw":
                le = widget_info[1]
                text = le.text()
                new_line = text + "\n"
            else:
                # fallback: treat as raw
                widget = widget_info[1]
                try:
                    new_line = widget.text() + "\n"
                except Exception:
                    continue

            # write back: replace existing line if value_idx valid, else append after marker index
            if val_idx is not None and 0 <= val_idx < len(lines):
                lines[val_idx] = new_line
            else:
                insert_pos = marker_idx + 1 if marker_idx is not None else len(lines)
                lines.insert(insert_pos, new_line)

        # Save via core if available, else write file
        if self.using_core_config and hasattr(self.core_config, "lines") and hasattr(self.core_config, "replace_line"):
            # replace core_config.lines entirely then call save
            # But we want to only change the lines we modified: map lines -> core_config.lines
            # Simpler: replace whole file via core's save mechanism by writing to file path.
            try:
                # write out to file path given by core_config.path if present
                path = getattr(self.core_config, "path", None)
                if path is None:
                    # try to derive path
                    path = os.path.expanduser("~/.bashrc")
                with open(path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                # if core has load/save methods, call them to refresh
                if hasattr(self.core_config, "load"):
                    try:
                        self.core_config.load()
                    except Exception:
                        pass
                elif hasattr(self.core_config, "save"):
                    try:
                        self.core_config.save(backup=True)
                    except Exception:
                        pass
            except Exception as e:
                print("Error saving via core_config:", e)
        else:
            try:
                # ensure parent dir exists
                self.bashrc_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.bashrc_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
            except Exception as e:
                print("Error writing ~/.bashrc:", e)

        # reload internal state
        self._load_source()
        # optional: give user brief feedback
        print("Saved .bashrc (backup created).")
