@echo off
echo ========================================================
echo            SIMPLE RELAY GUI APPLICATION
echo ========================================================
echo Setting up environment for FT232H...
set BLINKA_FT232H=1
set PYFTDI_BACKEND=libusb1

echo Activating virtual environment if it exists...
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else (
    echo Virtual environment not found. Continuing without venv.
)

echo Checking for processes using libusb...
taskkill /F /IM python.exe /T 2>nul
timeout /t 1 /nobreak >nul

echo Checking for FT232H device...
REM Use Python with -S flag to prevent importing site module (which adds current dir to path)
python -S -c "import sys; sys.path.append('.'); import usb.core; exit(0 if usb.core.find(idVendor=0x0403, idProduct=0x6014) else 1)"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: No FT232H device found!
    echo Please check the connection and drivers.
    echo.
    pause
    exit /b 1
)

echo FT232H device found!
echo Resetting device...
REM Use Python with -S flag to prevent importing site module (which adds current dir to path)
python -S -c "import sys; sys.path.append('.'); import usb.core; dev=usb.core.find(idVendor=0x0403,idProduct=0x6014); dev.reset(); print('Device reset successfully') if dev else print('No device found')"
timeout /t 2 /nobreak >nul

echo Running Relay GUI Application...
echo ========================================================
REM Use Python with -S flag to prevent importing site module (which adds current dir to path)
python -S GUI.py

echo.
echo Application closed. Press any key to exit.
pause >nul
