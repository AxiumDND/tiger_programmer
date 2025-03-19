"""
main.py

This is the entry point of the application. It creates the main window,
sets up a tabbed interface with two pages (Levels Sheet and Relay Control),
and includes a global log area at the bottom with a fixed height.
A dark theme is applied using the Fusion style and a custom dark palette.
"""

import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
)
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt

# Set environment variables for the FTDI device
os.environ["BLINKA_FT232H"] = "1"  # Enable FTDI support in Blinka
os.environ["PYFTDI_BACKEND"] = "libusb1"  # Use libusb1 as the backend for PyFTDI

from relay_control import RelayControlApp
from levels_sheet_page import LevelsSheetPage
from gui_logger import set_global_log_widget, clear_global_log

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Levels Sheet and Relay Control")
        self.resize(1366, 768)
        
        # Create the main widget and layout.
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        
        # Create a tab widget to hold the Levels Sheet and Relay Control pages.
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Instantiate the pages.
        self.relay_control_app = RelayControlApp()
        self.levels_sheet_page = LevelsSheetPage(self.tabs, relay_controller=self.relay_control_app)
        
        # Add pages as tabs.
        self.tabs.addTab(self.levels_sheet_page, "Levels Sheet")
        self.tabs.addTab(self.relay_control_app, "Relay Control")
        
        # Create a global log area (QTextEdit) with a fixed height.
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setFixedHeight(150)  # Limits the logger's vertical space.
        main_layout.addWidget(self.log_widget)
        
        # Set the global log widget so the logging module can write messages.
        set_global_log_widget(self.log_widget)
        
        # Add a Clear Log button.
        button_layout = QHBoxLayout()
        button_layout.addStretch()  # Push the button to the right.
        clear_button = QPushButton("Clear Log")
        clear_button.clicked.connect(self.clear_log)
        button_layout.addWidget(clear_button)
        main_layout.addLayout(button_layout)
        
        # Set the main widget as the central widget.
        self.setCentralWidget(main_widget)
        
    def clear_log(self):
        """Clear the global log widget."""
        clear_global_log()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Apply the Fusion style for a modern look.
    app.setStyle("Fusion")
    
    # Create and set a dark palette.
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.WindowText, Qt.white)
    dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.Text, Qt.white)
    dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(dark_palette)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
