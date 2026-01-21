# =========================
# SharkPad main.py
# Full features + fixed voice speed/accuracy + voice indicator checkbox
# FIXED: Prevents extra process spawning on macOS
# =========================

import sys
import os

# CRITICAL: Must be at the very top for macOS PyInstaller builds
import multiprocessing
if __name__ == '__main__':
    multiprocessing.freeze_support()

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPlainTextEdit, QMenu, QWidget, QHBoxLayout, QVBoxLayout,
    QFileDialog, QMessageBox, QProgressBar, QLabel, QSlider, QDialog, QPushButton, QLineEdit,
    QCheckBox, QWidgetAction
)
from PySide6.QtGui import QFont, QFontDatabase, QKeySequence, QShortcut, QIcon, QAction
from PySide6.QtCore import Qt, QTimer, QSettings

import file_operations
import view_operations
import preferences_operations
import ai_operations
import voice_operations
import drawing_operations
import summarization_operations
from splash import SplashScreen

# -----------------------------
# PyInstaller-safe resource path
# -----------------------------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# -----------------------------
# AI Settings Dialog
# -----------------------------
class OpenAISettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Teacher Settings")
        self.setFixedWidth(450)
        self.settings = QSettings("SharkPadApp", "Settings")
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("<b>Setup AI Teacher</b>"))

        link = QLabel('<a href="https://console.groq.com/keys">Get a free Groq API key</a>')
        link.setOpenExternalLinks(True)
        layout.addWidget(link)

        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_input.setText(self.settings.value("api_key", ""))
        self.token_input.setPlaceholderText("gsk_...")
        layout.addWidget(self.token_input)

        btns = QHBoxLayout()
        btns.addStretch()

        cancel = QPushButton("Cancel")
        save = QPushButton("Save Key")
        save.setStyleSheet("background:#4CAF50;color:white;font-weight:bold;")

        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.save_token)

        btns.addWidget(cancel)
        btns.addWidget(save)
        layout.addLayout(btns)

    def save_token(self):
        token = self.token_input.text().strip()
        if not token.startswith("gsk_"):
            QMessageBox.warning(self, "Invalid Key", "Groq API keys must start with gsk_")
            return
        self.settings.setValue("api_key", token)
        summarization_operations.set_api_token(token)
        QMessageBox.information(self, "Saved", "API key saved")
        self.accept()

# -----------------------------
# Mic Sensitivity Dialog
# -----------------------------
class MicSensitivityDialog(QDialog):
    def __init__(self, parent=None, current_value=50):
        super().__init__(parent)
        self.setWindowTitle("Microphone Sensitivity")
        self.resize(400, 200)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Adjust sensitivity for your environment\n"
            "Watch the audio level meter to find the optimal setting"
        ))

        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        layout.addWidget(self.level_bar)

        self.slider_label = QLabel(f"Sensitivity: {current_value}%")
        layout.addWidget(self.slider_label)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(current_value)

        def update(value):
            self.slider_label.setText(f"Sensitivity: {value}%")
            # Convert 0-100 to 4000-100 range (INVERTED - higher % = more sensitive = lower threshold)
            actual_value = int(4000 - (value / 100) * 3900)
            voice_operations.set_sensitivity(actual_value)

        self.slider.valueChanged.connect(update)
        layout.addWidget(self.slider)

        self.optimal_label = QLabel("Optimal: 40-60% for most environments")
        self.optimal_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        layout.addWidget(self.optimal_label)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def update_level(self, level):
        self.level_bar.setValue(level)

# -----------------------------
# Dyslexia Fonts
# -----------------------------
def load_dyslexia_fonts():
    r = QFontDatabase.addApplicationFont(resource_path("OpenDyslexic-Regular.ttf"))
    b = QFontDatabase.addApplicationFont(resource_path("OpenDyslexic-Bold.ttf"))
    rf = QFontDatabase.applicationFontFamilies(r)[0] if r != -1 else "Arial"
    bf = QFontDatabase.applicationFontFamilies(b)[0] if b != -1 else "Arial"
    return rf, bf

# -----------------------------
# File helper functions
# -----------------------------
def open_file(editor, parent, drawing_pad=None):
    return file_operations.open_file(editor, parent, drawing_pad)

def save_file(editor, parent, current_file=None, drawing_pad=None):
    return file_operations.save_file(editor, parent, current_file, drawing_pad)

def save_file_as(editor, parent, drawing_pad=None):
    return file_operations.save_file_as(editor, parent, drawing_pad)

# -----------------------------
# Main initialization
# -----------------------------
def init_main():
    window = QMainWindow()
    window.setWindowTitle("SharkPad")
    window.resize(900, 600)
    window.setWindowIcon(QIcon(resource_path("shark_pad_icon.png")))

    settings = QSettings("SharkPadApp", "Settings")
    editor = QPlainTextEdit()
    editor.setPlaceholderText("Welcome to SharkPad. Start writing…")
    editor.setFont(QFont("Arial", int(settings.value("font_size", 14))))

    drawing_pad = drawing_operations.create_drawing_pad()

    central = QWidget()
    layout = QHBoxLayout(central)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(editor)
    layout.addWidget(drawing_pad)
    window.setCentralWidget(central)

    # Auto-load API key
    if settings.value("api_key"):
        summarization_operations.set_api_token(settings.value("api_key"))

    # Theme
    preferences_operations.apply_theme(editor, settings.value("theme", "Light"))

    current_file = [None]
    mic_dialog = [None]
    current_sensitivity = [50]  # Now 0-100 scale

    menu = window.menuBar()

    # ---------------- File Menu ----------------
    file_menu = menu.addMenu("File")
    new_action = QAction("New", window)
    open_action = QAction("Open", window)
    save_action = QAction("Save", window)
    save_as_action = QAction("Save As", window)

    new_action.triggered.connect(lambda: editor.clear() or drawing_pad.canvas.clear_canvas())
    open_action.triggered.connect(lambda: open_file(editor, window, drawing_pad))
    save_action.triggered.connect(lambda: save_file(editor, window, current_file[0], drawing_pad))
    save_as_action.triggered.connect(lambda: save_file_as(editor, window, drawing_pad))

    file_menu.addActions([new_action, open_action, save_action, save_as_action])

    # ---------------- View Menu ----------------
    view_menu = menu.addMenu("View")
    wrap_action = QAction("Word Wrap", window, checkable=True, checked=True)
    wrap_action.triggered.connect(lambda: view_operations.toggle_word_wrap(editor))
    view_menu.addAction(wrap_action)

    set_font_action = QAction("Set Font Size...", window)
    view_menu.addAction(set_font_action)
    font_size_indicator = QAction(f"Font Size: {editor.font().pointSize()}", window)
    font_size_indicator.setDisabled(True)
    view_menu.addAction(font_size_indicator)

    def change_font_trigger():
        new_size = view_operations.set_font_size(editor, window)
        font_size_indicator.setText(f"Font Size: {new_size}")
        settings.setValue("font_size", new_size)

    set_font_action.triggered.connect(change_font_trigger)

    drawing_pad_action = QAction("Show Drawing Pad", window, checkable=True, checked=True)
    drawing_pad_action.triggered.connect(lambda: drawing_pad.setVisible(drawing_pad_action.isChecked()))
    view_menu.addAction(drawing_pad_action)

    # ---------------- Dyslexia Font Menu ----------------
    dyslexia_menu = QMenu("Dyslexia Font", window)
    dyslexia_off_action = QAction("Off", window, checkable=True, checked=True)
    dyslexia_regular_action = QAction("Regular", window, checkable=True)
    dyslexia_bold_action = QAction("Bold", window, checkable=True)

    def select_dyslexia_font(selected):
        for act in [dyslexia_off_action, dyslexia_regular_action, dyslexia_bold_action]:
            act.setChecked(False)
        selected.setChecked(True)
        f = QFont(editor.font())
        if dyslexia_regular_action.isChecked():
            f.setFamily(dyslexia_regular_family)
            f.setBold(False)
        elif dyslexia_bold_action.isChecked():
            f.setFamily(dyslexia_bold_family)
            f.setBold(True)
        else:
            f.setFamily("Arial")
            f.setBold(False)
        editor.setFont(f)

    dyslexia_off_action.triggered.connect(lambda: select_dyslexia_font(dyslexia_off_action))
    dyslexia_regular_action.triggered.connect(lambda: select_dyslexia_font(dyslexia_regular_action))
    dyslexia_bold_action.triggered.connect(lambda: select_dyslexia_font(dyslexia_bold_action))
    dyslexia_menu.addActions([dyslexia_off_action, dyslexia_regular_action, dyslexia_bold_action])
    view_menu.addMenu(dyslexia_menu)

    # ---------------- Preferences Menu ----------------
    pref_menu = menu.addMenu("Preferences")
    themes_menu = QMenu("Color Scheme", window)
    for t in ["Light", "Dark", "Solarized"]:
        act = QAction(t, window)
        act.triggered.connect(lambda _, theme=t: preferences_operations.apply_theme(editor, theme) or settings.setValue("theme", theme))
        themes_menu.addAction(act)
    pref_menu.addMenu(themes_menu)

    # ---------------- AI Menu ----------------
    ai_menu = menu.addMenu("AI Tools")
    ai_settings_action = QAction("AI Teacher Settings...", window)
    ai_settings_action.triggered.connect(lambda: OpenAISettingsDialog(window).exec())
    ai_menu.addAction(ai_settings_action)

    # --- Voice Dictation Toggle ---
    voice_action = QAction("Start Voice Dictation", window)
    ai_menu.addAction(voice_action)

    def toggle_voice_ui():
        def level_cb(l):
            if mic_dialog[0] and mic_dialog[0].isVisible(): mic_dialog[0].update_level(l)
        # Convert 0-100 sensitivity to 4000-100 range (INVERTED - higher % = more sensitive)
        actual_sensitivity = int(4000 - (current_sensitivity[0] / 100) * 3900)
        on = voice_operations.toggle_voice(editor, level_cb, actual_sensitivity)
        if on:
            voice_action.setText("Stop Voice Dictation")
            window.setWindowTitle("SharkPad — Listening...")
            if mic_dialog[0]: 
                mic_dialog[0].show()
        else:
            voice_action.setText("Start Voice Dictation")
            window.setWindowTitle("SharkPad")
            if mic_dialog[0]: 
                mic_dialog[0].close()
    
    voice_action.triggered.connect(toggle_voice_ui)

    mic_action = QAction("Microphone Sensitivity", window)
    mic_action.triggered.connect(lambda: (mic_dialog.__setitem__(0, MicSensitivityDialog(window, current_sensitivity[0])) or mic_dialog[0].show()) if not mic_dialog[0] else mic_dialog[0].show())
    ai_menu.addAction(mic_action)

    summarize_action = QAction("AI Teacher Explain", window)
    def summarize_text_trigger():
        text = editor.toPlainText()
        if not text.strip(): return QMessageBox.information(window, "No Text", "Please provide content!")
        window.setWindowTitle("SharkPad — Teacher thinking...")
        QApplication.processEvents()
        summary = summarization_operations.summarize_text(text, max_sentences=5)
        editor.setPlainText(summary)
        window.setWindowTitle("SharkPad")
        QMessageBox.information(window, "AI Teacher", "Explanation complete!")
    summarize_action.triggered.connect(summarize_text_trigger)
    ai_menu.addAction(summarize_action)

    # ---------------- Shortcuts ----------------
    QShortcut(QKeySequence("Ctrl+O"), window, lambda: open_file(editor, window, drawing_pad))
    QShortcut(QKeySequence("Ctrl+S"), window, lambda: save_file(editor, window, current_file[0], drawing_pad))
    QShortcut(QKeySequence("Ctrl+Shift+S"), window, lambda: save_file_as(editor, window, drawing_pad))
    QShortcut(QKeySequence("Ctrl+Shift+V"), window, toggle_voice_ui)
    QShortcut(QKeySequence("Ctrl+Shift+T"), window, summarize_text_trigger)
    QShortcut(QKeySequence("Ctrl+Shift+D"), window, lambda: drawing_pad.set_mode('draw'))
    QShortcut(QKeySequence("Ctrl+Shift+E"), window, drawing_pad.canvas.set_eraser)

    ai_operations.enable_spellcheck(editor)
    window.show()
    
    return window

# -----------------------------
# App Entry Point
# -----------------------------
if __name__ == '__main__':
    app = QApplication(sys.argv)
    dyslexia_regular_family, dyslexia_bold_family = load_dyslexia_fonts()
    splash = SplashScreen(width=600, height=300)
    splash.show_splash()

    def boot():
        ai_operations.spell.unknown(["shark"])
        window = init_main()
        QTimer.singleShot(800, splash.close)

    QTimer.singleShot(100, boot)
    sys.exit(app.exec())