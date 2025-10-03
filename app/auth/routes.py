# app/auth/routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from app.models import db, User
from flask_bcrypt import Bcrypt
from flask_login import login_user, logout_user, login_required, current_user
from app.utils import log_activity


bp = Blueprint('auth', __name__, template_folder='templates', url_prefix='/auth')
bcrypt = Bcrypt()

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)

            # Logowanie aktywności
            log_activity("Zalogował się do systemu.")
            db.session.commit() # Commit jest potrzebny, aby zapisać log przed przekierowaniem
            
            flash('Zalogowano pomyślnie!', 'success')
            return redirect(url_for('main.home'))
        else:
            flash('Nieprawidłowa nazwa użytkownika lub hasło.', 'danger')
    return render_template('login.html')


@bp.route('/logout')
@login_required
def logout():
    # Logowanie aktywności PRZED wylogowaniem
    log_activity("Wylogował się z systemu.")
    db.session.commit() # Commit jest potrzebny, bo sesja użytkownika zaraz wygaśnie

    logout_user()
    flash('Wylogowano pomyślnie.', 'info')
    return redirect(url_for('auth.login'))