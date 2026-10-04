@echo off
REM One-command start (Windows): creates a venv, installs dependencies, runs SafetyCheck.
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python run.py
