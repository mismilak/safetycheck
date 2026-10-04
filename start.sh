#!/usr/bin/env bash
# One-command start (Linux/macOS): creates a venv, installs dependencies, runs SafetyCheck.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
python run.py
