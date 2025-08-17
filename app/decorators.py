# app/decorators.py
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            # Admin ma dostęp do wszystkiego
            if current_user.has_role('admin'):
                return f(*args, **kwargs)
            
            if not current_user.has_role(permission):
                flash('Brak uprawnień do dostępu do tej strony.', 'danger')
                # POPRAWKA: Przekierowujemy na bezpieczną stronę główną
                return redirect(url_for('main.home')) 
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator