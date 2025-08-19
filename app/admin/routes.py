# app/admin/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, User, Role, Task, ProductionOrder, FinishedProduct
from flask_login import login_required, current_user
from app.decorators import permission_required
from app.auth.routes import bcrypt
from sqlalchemy import func
from datetime import datetime, timedelta

bp = Blueprint('admin', __name__, template_folder='templates', url_prefix='/admin')

@bp.route('/users', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def manage_users():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        existing_user = User.query.filter_by(username=username).first()
        existing_email = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Użytkownik o tej nazwie już istnieje.', 'warning')
        elif existing_email:
            flash('Ten adres e-mail jest już używany.', 'warning')
        else:
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            new_user = User(username=username, email=email, password_hash=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            flash(f"Utworzono użytkownika: {username}", "success")
        return redirect(url_for('admin.manage_users'))
    users = User.query.order_by(User.username).all()
    roles = Role.query.all()
    return render_template('manage_users.html', users=users, roles=roles)

@bp.route('/assign_roles/<int:user_id>', methods=['POST'])
@login_required
@permission_required('admin')
def assign_roles(user_id):
    user = User.query.get_or_404(user_id)
    assigned_role_ids = [int(role_id) for role_id in request.form.getlist('roles')]
    user.roles = Role.query.filter(Role.id.in_(assigned_role_ids)).all()
    db.session.commit()
    flash(f"Zaktualizowano role dla użytkownika {user.username}.", "success")
    return redirect(url_for('admin.manage_users'))

@bp.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def edit_user(user_id):
    user_to_edit = User.query.get_or_404(user_id)
    if request.method == 'POST':
        new_username = request.form.get('username')
        new_email = request.form.get('email')
        if new_username != user_to_edit.username and User.query.filter_by(username=new_username).first():
            flash('Ta nazwa użytkownika jest już zajęta.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))
        if new_email != user_to_edit.email and User.query.filter_by(email=new_email).first():
            flash('Ten adres e-mail jest już używany.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))
        user_to_edit.username = new_username
        user_to_edit.email = new_email
        db.session.commit()
        flash(f"Dane użytkownika {user_to_edit.username} zostały zaktualizowane.", "success")
        return redirect(url_for('admin.manage_users'))
    return render_template('edit_user.html', user=user_to_edit)

@bp.route('/change_password/<int:user_id>', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def change_password(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if not new_password or new_password != confirm_password:
            flash("Hasła muszą być takie same i nie mogą być puste.", "danger")
            return redirect(url_for('admin.change_password', user_id=user_id))
        user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        db.session.commit()
        flash(f"Hasło dla użytkownika {user.username} zostało pomyślnie zmienione.", "success")
        return redirect(url_for('admin.manage_users'))
    return render_template('change_password.html', user=user)

@bp.route('/all_tasks')
@login_required
@permission_required('admin')
def all_tasks():
    tasks = Task.query.order_by(Task.creation_date.desc()).all()
    return render_template('all_tasks.html', tasks=tasks)

@bp.route('/statistics')
@login_required
@permission_required('admin')
def statistics():
    # Sprawdzamy, jakiego dialektu bazy danych używamy
    db_dialect = db.engine.dialect.name

    if db_dialect == 'postgresql':
        # Wersja dla PostgreSQL (produkcja)
        date_func_daily = func.to_char(ProductionOrder.order_date, 'YYYY-MM-DD')
        date_func_weekly = func.to_char(ProductionOrder.order_date, 'YYYY-WW')
        date_func_monthly = func.to_char(ProductionOrder.order_date, 'YYYY-MM')
    else:
        # Wersja dla SQLite (lokalnie)
        date_func_daily = func.date(ProductionOrder.order_date)
        date_func_weekly = func.strftime('%Y-%W', ProductionOrder.order_date)
        date_func_monthly = func.strftime('%Y-%m', ProductionOrder.order_date)

    # Statystyki dzienne
    daily_stats = db.session.query(
        date_func_daily.label('date'),
        FinishedProduct.name.label('product_name'),
        func.sum(ProductionOrder.quantity_produced).label('total_quantity')
    ).join(FinishedProduct).group_by('date', 'product_name').order_by(db.desc('date')).all()

    # Statystyki tygodniowe
    weekly_stats = db.session.query(
        date_func_weekly.label('week'),
        FinishedProduct.name.label('product_name'),
        func.sum(ProductionOrder.quantity_produced).label('total_quantity')
    ).join(FinishedProduct).group_by('week', 'product_name').order_by(db.desc('week')).all()
    
    # Statystyki miesięczne
    monthly_stats = db.session.query(
        date_func_monthly.label('month'),
        FinishedProduct.name.label('product_name'),
        func.sum(ProductionOrder.quantity_produced).label('total_quantity')
    ).join(FinishedProduct).group_by('month', 'product_name').order_by(db.desc('month')).all()

    return render_template(
        'statistics.html', 
        daily_stats=daily_stats,
        weekly_stats=weekly_stats,
        monthly_stats=monthly_stats
    )