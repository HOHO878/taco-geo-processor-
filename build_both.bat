REM Batch script to build both 32-bit and 64-bit executables using PyInstaller
REM Ensure you are in the correct directory before running this script

REM Build 32-bit version
pyinstaller tacox32.spec

REM Build 64-bit version
pyinstaller tacox64.spec

echo Build complete. Check the 'dist' folder for taco32 and taco64 folders.
pause
