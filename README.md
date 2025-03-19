# Tiger Programmer V2

A GUI application for controlling relay systems with FT232H interface.

## Features
- Relay control interface
- FT232H hardware integration
- CSV data import/export
- Logging system
- User-friendly GUI

## Requirements
- Python 3.x
- FT232H USB device
- Required Python packages (see requirements.txt)

## Installation
1. Clone this repository
2. Install required packages:
   ```
   pip install -r requirements.txt
   ```
3. Connect FT232H device
4. Run `program_start.bat`

## Usage
1. Launch the application using `program_start.bat`
2. Use the GUI interface to control relays
3. Import/export data using CSV files

## Version History

### v1.0.0 (2024-03-19) - Initial Release
#### Core Features
- Basic relay control functionality through GUI interface
- FT232H hardware integration with error handling
- CSV data import/export capabilities
- Comprehensive logging system

#### Components
- `Gui.py`: Main GUI interface with relay controls
- `relay_control.py`: Core relay control logic
- `levels_sheet_page.py`: Sheet management interface
- `program_start.bat`: Application launcher with environment setup
- `main.py`: Application entry point and initialization

#### Technical Details
- Python-based implementation
- Uses Adafruit's FT232H libraries
- Includes error handling for hardware disconnection
- Automated logging system for debugging

#### Dependencies
- pyusb >= 1.0.2
- pyftdi >= 0.53.3
- adafruit-blinka >= 8.0.0
- adafruit-circuitpython-ft232h >= 2.0.0

### Future Versions
#### Planned for v1.1.0
- Enhanced error handling
- Additional hardware support
- UI improvements
- Performance optimizations

#### Planned for v1.2.0
- Extended CSV functionality
- Additional data export formats
- User configuration options

## License
[Your chosen license]

## Author
AxiumDND 