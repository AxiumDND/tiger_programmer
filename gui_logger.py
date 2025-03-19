"""
gui_logger.py

This module provides a global logging utility that writes messages to a
global log widget. If the widget is not set, messages are printed to the console.
"""

from PyQt5.QtCore import QObject, pyqtSignal, QMetaType

# Register QTextCursor type for cross-thread signal/slot
try:
    from PyQt5.QtCore import qRegisterMetaType
    qRegisterMetaType('QTextCursor')
except (ImportError, TypeError):
    pass  # Ignore if registration fails

# Logger class to handle cross-thread logging
class Logger(QObject):
    # Signal to safely update log from any thread
    log_signal = pyqtSignal(str)
    clear_signal = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.widget = None
        
    def set_widget(self, widget):
        """Set the log widget and connect signals"""
        self.widget = widget
        self.log_signal.connect(self._append_to_widget)
        self.clear_signal.connect(self._clear_widget)
        
    def log(self, message):
        """Log a message (thread-safe)"""
        if self.widget:
            self.log_signal.emit(message)
        else:
            print(message)
            
    def clear(self):
        """Clear the log (thread-safe)"""
        if self.widget:
            self.clear_signal.emit()
            
    def _append_to_widget(self, message):
        """Slot to append text to widget (runs in GUI thread)"""
        if self.widget:
            self.widget.append(message)
            
    def _clear_widget(self):
        """Slot to clear widget (runs in GUI thread)"""
        if self.widget:
            self.widget.clear()

# Create a global logger instance
_logger = Logger()

def set_global_log_widget(widget):
    """
    Set the global log widget used for displaying log messages.
    
    Args:
        widget: A QTextEdit (or similar) widget that supports appending text.
    """
    _logger.set_widget(widget)

def global_log(message):
    """
    Append a log message to the global log widget.
    
    Args:
        message: The log message as a string.
    """
    _logger.log(message)

def clear_global_log():
    """
    Clear all messages from the global log widget.
    """
    _logger.clear()
