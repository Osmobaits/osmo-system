from app import create_app
from app.models import db
import sqlalchemy

def fix():
    app = create_app()
    with app.app_context():
        print("Rozpoczynam naprawę wersji bazy danych...")
        try:
            # Ręczne ustawienie wersji na ostatnią poprawną
            sql = sqlalchemy.text("UPDATE alembic_version SET version_num = '60da692b8fb2'")
            db.session.execute(sql)
            db.session.commit()
            print("SUKCES: Wersja bazy została ustawiona na 60da692b8fb2")
        except Exception as e:
            print(f"BŁĄD lub brak tabeli wersji: {e}")
            
if __name__ == "__main__":
    fix()