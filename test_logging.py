import sys
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")

try:
    import logging
    print(f"Logging module: {logging}")
    print(f"getLogger exists: {'getLogger' in dir(logging)}")
    print(f"Logger exists: {'Logger' in dir(logging)}")
    print(dir(logging))
except Exception as e:
    print(f"Error importing logging: {e}")
