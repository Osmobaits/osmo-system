import os

class Config:
    # Klucz do zabezpieczania sesji i formularzy
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'domyslny-tajny-klucz-zmien-to'

    # Konfiguracja bazy danych
    # Na serwerze Render odczyta adres z zmiennej środowiskowej DATABASE_URL.
    # Lokalnie na Twoim komputerze użyje pliku osmo_database.db.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///osmo_database.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Konfiguracja folderu na załączniki
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')

    # === KONFIGURACJA POCZTY E-MAIL ===
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'osmobaits@gmail.com'  # <-- WPISZ SWÓJ ADRES GMAIL
    MAIL_PASSWORD = 'vsnqcuaxdsnqdemk'      # <-- WKLEJ 16-ZNAKOWE HASŁO DO APLIKACJI
    MAIL_DEFAULT_SENDER = 'osmobaits@gmail.com'