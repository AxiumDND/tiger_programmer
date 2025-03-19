import sys
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")

try:
    import usb
    print(f"USB module: {usb}")
    print(f"USB module path: {usb.__file__}")
    
    import usb.core
    print(f"USB core module: {usb.core}")
    print(f"USB core module path: {usb.core.__file__}")
    
    try:
        device = usb.core.find(idVendor=0x0403, idProduct=0x6014)
        if device:
            print(f"Found device: {device}")
        else:
            print("No device found")
    except Exception as e:
        print(f"Error finding device: {e}")
        
except Exception as e:
    print(f"Error importing USB: {e}")
