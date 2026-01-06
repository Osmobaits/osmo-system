#!/bin/bash
set -o errexit

# 1. Instalacja zależności
pip install -r requirements.txt

# 2. Ręczna korekta wersji migracji w bazie danych Postgres
python << END
from app import create_app
from app.models import db
import sqlalchemy

app = create_app()
with app.app_context():
    # Używamy text() dla bezpieczeństwa zapytania
    sql = sqlalchemy.text("UPDATE alembic_version SET version_num = '60da692b8fb2'")
    db.session.execute(sql)
    db.session.commit()
    print("Sukces: Wersja migracji w bazie Postgres zmieniona na 60da692b8fb2")
END

# 3. Uruchomienie właściwej aktualizacji bazy danych
flask db upgrade