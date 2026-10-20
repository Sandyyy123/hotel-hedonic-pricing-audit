#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3.11 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python main.py
.venv/bin/python -m pytest -q
