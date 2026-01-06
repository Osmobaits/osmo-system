#!/bin/bash
set -o errexit

# 1. Instalacja zależności
pip install -r requirements.txt

# 2. Ręczna korekta wersji migracji w bazie danych Postgres
# Używamy Pythona, aby załadować aplikację i wykonać zapytanie SQL
python -c 'from app import create_app; from app.models import db; app = create_app(); with app.app_context(): db.session.execute(db.text("UPDATE alembic_version SET version_num = \"60da692b8fb2\"")); db.session.commit(); print("Wersja migracji została pomyślnie zaktualizowana na 60da692b8fb2")'

# 3. Uruchomienie właściwej aktualizacji bazy danych
flask db upgrade