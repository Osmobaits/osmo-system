# app/__init__.py
from flask import Flask
from config import Config
from .models import db, User, Role
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_migrate import Migrate # <-- NOWY IMPORT
import click
from datetime import timezone, timedelta

login_manager = LoginManager()
bcrypt = Bcrypt()
mail = Mail()
migrate = Migrate() # <-- NOWY OBIEKT

def format_datetime_local(dt):
    if dt is None:
        return ""
    cest = timezone(timedelta(hours=2))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(cest).strftime('%Y-%m-%d %H:%M')

def format_day_of_week(dt):
    if dt is None:
        return ""
    days = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
    return days[dt.weekday()]

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.template_folder = 'templates'
    
    db.init_app(app)
    migrate.init_app(app, db) # <-- INICJALIZACJA
    login_manager.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)

    app.jinja_env.filters['localdatetime'] = format_datetime_local
    app.jinja_env.filters['dayofweek'] = format_day_of_week

    login_manager.login_view = 'auth.login'
    
    with app.app_context():
        from .warehouse import routes as warehouse_routes
        app.register_blueprint(warehouse_routes.bp)
        from .production import routes as production_routes
        app.register_blueprint(production_routes.bp)
        from .orders import routes as orders_routes
        app.register_blueprint(orders_routes.bp)
        from .auth import routes as auth_routes
        app.register_blueprint(auth_routes.bp)
        from .admin import routes as admin_routes
        app.register_blueprint(admin_routes.bp)
        from .main import routes as main_routes
        app.register_blueprint(main_routes.bp)
        from .tasks import routes as tasks_routes
        app.register_blueprint(tasks_routes.bp)
        
    @app.cli.command("init-db")
    def init_db_command():
        """Tworzy tabele, role i pierwszego admina."""
        db.create_all()
        role_names = ['admin', 'warehouse', 'production', 'orders', 'tasks']
        for name in role_names:
            if not Role.query.filter_by(name=name).first():
                db.session.add(Role(name=name))
        db.session.commit()
        if not User.query.filter_by(username='admin').first():
            admin_role = Role.query.filter_by(name='admin').first()
            if admin_role:
                hashed_password = bcrypt.generate_password_hash('admin').decode('utf-8')
                admin_user = User(username='admin', password_hash=hashed_password, email='twoj.admin@email.com', roles=[admin_role])
                db.session.add(admin_user)
        db.session.commit()
        print("Baza danych zainicjalizowana z rolami i użytkownikiem admin.")

    return app

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))