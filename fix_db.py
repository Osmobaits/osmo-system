import os
import sqlalchemy
from sqlalchemy import create_engine, text

def fix():
    # Pobranie DATABASE_URL z Render
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("BŁĄD: Brak zmiennej DATABASE_URL")
        return

    # Korekta protokołu dla SQLAlchemy (Render używa postgres://)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)
    
    with engine.connect() as connection:
        # Rozpoczynamy transakcję
        trans = connection.begin()
        try:
            print("--- ROZPOCZYNAM FORSOWNE PATCHOWANIE BAZY ---")
            
            # 1. Dodajemy kolumnę do raw_materials
            print("Próbuję dodać kolumnę unit_price do raw_materials...")
            connection.execute(text("ALTER TABLE raw_materials ADD COLUMN IF NOT EXISTS unit_price FLOAT DEFAULT 0.0;"))
            
            # 2. Dodajemy kolumnę do packaging
            print("Próbuję dodać kolumnę unit_price do packaging...")
            connection.execute(text("ALTER TABLE packaging ADD COLUMN IF NOT EXISTS unit_price FLOAT DEFAULT 0.0;"))

            # 3. Ustawiamy wersję Alembic (żeby system migracji się nie gubił)
            print("Aktualizuję tabelę alembic_version...")
            connection.execute(text("UPDATE alembic_version SET version_num = '60da692b8fb2';"))
            
            trans.commit()
            print("--- SUKCES: Kolumny zostały dodane, baza zsynchronizowana ---")
        except Exception as e:
            trans.rollback()
            print(f"--- KRYTYCZNY BŁĄD: {e} ---")

if __name__ == "__main__":
    fix()