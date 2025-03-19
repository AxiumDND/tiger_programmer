"""
custom_logging.py

This is a wrapper module that re-exports the standard Python logging module
while also providing the custom logging functionality from gui_logger.py.
"""

# Import and re-export the standard Python logging module
import sys
import importlib.util

# First, temporarily remove the current directory from sys.path to avoid circular imports
original_path = sys.path.copy()
if '' in sys.path:
    sys.path.remove('')
if '.' in sys.path:
    sys.path.remove('.')

# Import the standard logging module
import logging as standard_logging

# Restore the original path
sys.path = original_path

# Re-export all attributes from the standard logging module
for attr_name in dir(standard_logging):
    if not attr_name.startswith('__'):
        globals()[attr_name] = getattr(standard_logging, attr_name)

# Import and re-export our custom logging functionality
from gui_logger import set_global_log_widget, global_log, clear_global_log, Logger
