@echo off
echo Building Video Analyzer EXE...
pip install -r requirements.txt
pyinstaller --onefile --windowed --name VideoAnalyzer main.py
echo Build complete! EXE is in dist/VideoAnalyzer.exe
pause
