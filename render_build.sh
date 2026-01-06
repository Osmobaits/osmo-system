#!/bin/bash
set -o errexit
pip install -r requirements.txt
mkdir -p uploads  # <-- DODAJ TĘ LINIĘ
flask db upgrade