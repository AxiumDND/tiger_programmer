@echo on
echo ========================================================
echo            SIMPLE RELAY GUI APPLICATION
echo ========================================================

REM Create a log file
echo Starting program_start.bat at %date% %time% > program_start_log.txt
echo ======================================================== >> program_start_log.txt
echo            SIMPLE RELAY GUI APPLICATION >> program_start_log.txt
echo ======================================================== >> program_start_log.txt
echo Setting up environment for FT232H... >> program_start_log.txt
set BLINKA_FT232H=1
set PYFTDI_BACKEND=libusb1
echo Environment variables set: BLINKA_FT232H=%BLINKA_FT232H%, PYFTDI_BACKEND=%PYFTDI_BACKEND% >> program_start_log.txt

echo Activating virtual environment if it exists... >> program_start_log.txt
if exist venv\Scripts\activate.bat (
    echo Found virtual environment, activating... >> program_start_log.txt
    call venv\Scripts\activate.bat
    echo Virtual environment activated >> program_start_log.txt
) else (
    echo Virtual environment not found. Continuing without venv. >> program_start_log.txt
)

echo Checking for processes using libusb... >> program_start_log.txt
taskkill /F /IM python.exe /T 2>nul
timeout /t 1 /nobreak >nul
echo Processes checked >> program_start_log.txt

echo Checking for FT232H device... >> program_start_log.txt
REM Temporarily rename logging.py to avoid conflicts with standard library
if exist logging.py (
    echo Temporarily renaming logging.py to logging.py.bak... >> program_start_log.txt
    ren logging.py logging.py.bak
    if errorlevel 1 (
        echo Error renaming logging.py >> program_start_log.txt
        pause
        exit /b 1
    )
    echo Renamed logging.py to logging.py.bak >> program_start_log.txt
)

echo Running Python to check for FT232H device... >> program_start_log.txt
python -c "import usb.core; print('USB module imported successfully'); exit(0 if usb.core.find(idVendor=0x0403, idProduct=0x6014) else 1)" >> program_start_log.txt 2>&1
set PYTHON_RESULT=%ERRORLEVEL%
echo Python command completed with exit code: %PYTHON_RESULT% >> program_start_log.txt

REM Restore the original file
if exist logging.py.bak (
    echo Restoring logging.py... >> program_start_log.txt
    ren logging.py.bak logging.py
    if errorlevel 1 (
        echo Error restoring logging.py >> program_start_log.txt
        pause
        exit /b 1
    )
    echo Restored logging.py >> program_start_log.txt
)
if %PYTHON_RESULT% NEQ 0 (
    echo. >> program_start_log.txt
    echo WARNING: No FT232H device found! >> program_start_log.txt
    echo The application will continue, but hardware functionality will be limited. >> program_start_log.txt
    echo. >> program_start_log.txt
    echo.
    echo WARNING: No FT232H device found!
    echo The application will continue, but hardware functionality will be limited.
    echo.
    REM Continue execution instead of exiting
    REM pause
    REM exit /b 1
)

if %PYTHON_RESULT% == 0 (
    echo FT232H device found! >> program_start_log.txt
    echo FT232H device found!
) else (
    echo No FT232H device found, continuing with limited functionality... >> program_start_log.txt
    echo No FT232H device found, continuing with limited functionality...
)
echo Resetting device... >> program_start_log.txt
echo Resetting device...
REM Temporarily rename logging.py to avoid conflicts with standard library
if exist logging.py (
    echo Temporarily renaming logging.py to logging.py.bak... >> program_start_log.txt
    ren logging.py logging.py.bak
    if errorlevel 1 (
        echo Error renaming logging.py >> program_start_log.txt
        pause
        exit /b 1
    )
    echo Renamed logging.py to logging.py.bak >> program_start_log.txt
)

echo Running Python to reset FT232H device... >> program_start_log.txt
python -c "import usb.core; dev=usb.core.find(idVendor=0x0403,idProduct=0x6014); dev.reset() if dev else print('No device found'); print('Device reset successfully') if dev else print('No device found')" >> program_start_log.txt 2>&1
set PYTHON_RESET_RESULT=%ERRORLEVEL%
echo Python reset command completed with exit code: %PYTHON_RESET_RESULT% >> program_start_log.txt

REM Restore the original file
if exist logging.py.bak (
    echo Restoring logging.py... >> program_start_log.txt
    ren logging.py.bak logging.py
    if errorlevel 1 (
        echo Error restoring logging.py >> program_start_log.txt
        pause
        exit /b 1
    )
    echo Restored logging.py >> program_start_log.txt
)
echo Waiting 2 seconds... >> program_start_log.txt
timeout /t 2 /nobreak >nul
echo Wait completed >> program_start_log.txt

echo Running Relay GUI Application... >> program_start_log.txt
echo ======================================================== >> program_start_log.txt
echo Running Relay GUI Application...
echo ========================================================
REM Temporarily rename logging.py to avoid conflicts with standard library
if exist logging.py (
    echo Temporarily renaming logging.py to logging.py.bak... >> program_start_log.txt
    ren logging.py logging.py.bak
    if errorlevel 1 (
        echo Error renaming logging.py >> program_start_log.txt
        pause
        exit /b 1
    )
    echo Renamed logging.py to logging.py.bak >> program_start_log.txt
)

echo Starting main.py... >> program_start_log.txt
echo Starting main.py...
REM Run the main application
python main.py >> program_start_log.txt 2>&1
set PYTHON_MAIN_RESULT=%ERRORLEVEL%
echo Python main.py completed with exit code: %PYTHON_MAIN_RESULT% >> program_start_log.txt

if %PYTHON_MAIN_RESULT% NEQ 0 (
    echo Error running main.py >> program_start_log.txt
    echo Error running main.py
    if exist logging.py.bak (
        echo Restoring logging.py... >> program_start_log.txt
        ren logging.py.bak logging.py
        echo Restored logging.py >> program_start_log.txt
    )
    pause
    exit /b 1
)

REM Restore the original file
if exist logging.py.bak (
    echo Restoring logging.py... >> program_start_log.txt
    ren logging.py.bak logging.py
    if errorlevel 1 (
        echo Error restoring logging.py >> program_start_log.txt
        pause
        exit /b 1
    )
    echo Restored logging.py >> program_start_log.txt
)

echo Application completed successfully. >> program_start_log.txt
echo Application completed successfully.

echo.
echo Application closed. Press any key to exit.
pause >nul
