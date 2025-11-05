# app/__init__.py
from flask import Flask
from config import Config
# ZMIANA: Dodano 'TeamOrder'
from .models import db, User, Role, Task, TeamOrder
from flask_login import LoginManager, current_user
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_migrate import Migrate
import click
# ZMIANA: Import pytz
from datetime import timezone, timedelta
import pytz
from werkzeug.middleware.proxy_fix import ProxyFix

login_manager = LoginManager()
bcrypt = Bcrypt()
mail = Mail()
migrate = Migrate()

# ZMIANA: Zaktualizowana funkcja czasu
def format_datetime_local(dt):
    if dt is None:
        return ""
    
    # Użyj poprawnej strefy czasowej, która rozumie czas letni/zimowy
    local_tz = pytz.timezone('Europe/Warsaw')
    
    if dt.tzinfo is None:
        # Załóż, że czas w bazie danych jest w UTC
        dt = pytz.utc.localize(dt)
    
    # Konwertuj do czasu lokalnego (Warszawa)
    local_dt = dt.astimezone(local_tz)
    
    return local_dt.strftime('%Y-%m-%d %H:%M')

def format_day_of_week(dt):
    if dt is None:
        return ""
    days = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
    return days[dt.weekday()]

def create_app():
    app = Flask(__name__)
    
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    app.config.from_object(Config)
    app.template_folder = 'templates'
    
    db.init_app(app)
    migrate.init_app(app, db)
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
        from .finished_goods import routes as finished_goods_routes
        app.register_blueprint(finished_goods_routes.bp)
        from .auth import routes as auth_routes
        app.register_blueprint(auth_routes.bp)
        from .admin import routes as admin_routes
        app.register_blueprint(admin_routes.bp)
        from .main import routes as main_routes
        app.register_blueprint(main_routes.bp)
        from .tasks import routes as tasks_routes
        app.register_blueprint(tasks_routes.bp)
        from .vacations import routes as vacations_routes
        app.register_blueprint(vacations_routes.bp)
        from .packaging import routes as packaging_routes
        app.register_blueprint(packaging_routes.bp)
        from .reports import routes as reports_routes
        app.register_blueprint(reports_routes.bp)
        from .team_member import routes as team_member_routes
        app.register_blueprint(team_member_routes.bp)
        
        # --- NOWA LINIA ---
        from .debtor_tracker import routes as debtor_tracker_routes
        app.register_blueprint(debtor_tracker_routes.bp)
        # ------------------
        
    @app.cli.command("init-db")
    def init_db_command():
        """Tworzy tabele, role i pierwszego admina."""
        db.create_all()
        role_names = ['admin', 'warehouse', 'production', 'orders', 'tasks', 'vacations', 'team_member', 'team_orders']
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

    @app.cli.command("reset-admin-password")
    @click.argument("new_password")
    def reset_admin_password(new_password):
        """Resetuje hasło dla użytkownika 'admin'."""
        admin_user = User.query.filter_by(username='admin').first()
        if admin_user:
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            admin_user.password_hash = hashed_password
            db.session.commit()
            print("Hasło dla użytkownika 'admin' zostało pomyślnie zresetowane.")
        else:
            print("BŁĄD: Nie znaleziono użytkownika 'admin'.")

    @app.cli.command("assign-role")
    @click.argument("username")
    @click.argument("role_name")
    def assign_role(username, role_name):
        """Przypisuje rolę do użytkownika."""
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"BŁĄD: Nie znaleziono użytkownika '{username}'.")
            return
            
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            print(f"BŁĄD: Nie znaleziono roli '{role_name}'.")
            return

        if role in user.roles:
            print(f"Użytkownik '{username}' już ma rolę '{role_name}'.")
        else:
            user.roles.append(role)
            db.session.commit()
            print(f"Pomyślnie dodano rolę '{role_name}' do użytkownika '{username}'.")

    # === POCZĄTEK MODYFIKACJI ===
    @app.context_processor
    def inject_nav_counts():
        """Wstrzykuje liczbę nowych zadań i zamówień drużyny do wszystkich szablonów."""
        new_tasks_count = 0
        pending_team_orders_count = 0
        
        if current_user.is_authenticated:
            # Oblicz liczbę nowych zadań (dla wszystkich poza team_member)
            if not current_user.has_role('team_member'):
                try:
                    count = Task.query.filter(Task.assignees.contains(current_user), Task.status == 'Nowe').count()
                    new_tasks_count = count
                except Exception:
                    pass # Błąd bazy danych (np. przy starcie)

            # Oblicz liczbę zamówień drużyny (tylko dla admina)
            if current_user.has_role('admin'):
                try:
                    team_count = TeamOrder.query.filter_by(status='Oczekuje').count()
                    pending_team_orders_count = team_count
                except Exception:
                    pass # Błąd bazy danych (np. przy starcie)
                    
        return dict(
            new_tasks_count=new_tasks_count, 
            pending_team_orders_count=pending_team_orders_count
        )
    # === KONIEC MODYFIKACJI ===

    return app

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))