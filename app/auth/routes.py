from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, db
from app import bcrypt
from app.utils import log_activity

bp = Blueprint('auth', __name__, template_folder='templates', url_prefix='/auth')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # --- POPRAWIONA LOGIKA DLA JUŻ ZALOGOWANYCH ---
        if current_user.has_role('admin'):
            return redirect(url_for('main.dashboard'))
        elif current_user.has_role('team_member'):
            return redirect(url_for('team_member.dashboard'))
        else:
            return redirect(url_for('main.dashboard'))
        # ----------------------------------------------

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            log_activity("Zalogował się do systemu.")
            flash('Zalogowano pomyślnie!', 'success')

            # --- POPRAWIONA LOGIKA PRZEKIEROWANIA PO ZALOGOWANIU ---
            if current_user.has_role('admin'):
                return redirect(url_for('main.dashboard'))
            elif current_user.has_role('team_member'):
                return redirect(url_for('team_member.dashboard'))
            else:
                return redirect(url_for('main.dashboard'))
            # ----------------------------------------------------
        else:
            flash('Nieprawidłowa nazwa użytkownika lub hasło.', 'danger')
            
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    log_activity("Wylogował się z systemu.")
    logout_user()
    flash('Wylogowano pomyślnie.', 'info')
    return redirect(url_for('auth.login'))