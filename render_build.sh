#!/bin/bash
set -o errexit

# 1. Instalacja zależności
pip install -r requirements.txt

# 2. Tworzenie tymczasowego skryptu do naprawy wersji bazy
cat << 'EOF' > fix_db_version.py
from app import create_app
from app.models import db
import sqlalchemy

app = create_app()
with app.app_context():
    try:
        # Ustawiamy wskaźnik na ostatnią znaną dobrą wersję
        sql = sqlalchemy.text("UPDATE alembic_version SET version_num = '60da692b8fb2'")
        db.session.execute(sql)
        db.session.commit()
        print("--- Sukces: Wersja migracji w bazie Postgres ustawiona na 60da692b8fb2 ---")
    except Exception as e:
        print(f"--- Informacja: Nie udało się zaktualizować tabeli wersji (może jeszcze nie istnieć): {e} ---")
EOF

# 3. Uruchomienie skryptu naprawczego
python fix_db_version.py

# 4. Uruchomienie właściwej aktualizacji bazy (doda kolumnę unit_price)
flask db upgrade

# 5. Sprzątanie
rm fix_db_version.py