#!/bin/bash
set -o errexit
pip install -r requirements.txt
python fix_db.py
mkdir -p uploads  # <-- DODAJ TĘ LINIĘ
flask db upgrade