from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, User, Role, Task, ProductionOrder, FinishedProduct, TeamOrder, TeamOrderProduct
from flask_login import login_required, current_user, login_user
from app import bcrypt
from app.decorators import permission_required
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta
from app.utils import log_activity

bp = Blueprint('admin', __name__, template_folder='templates', url_prefix='/admin')

@bp.route('/users', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def manage_users():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Użytkownik o tej nazwie już istnieje.', 'danger')
        elif email and User.query.filter_by(email=email).first():
            flash('Ten adres e-mail jest już używany.', 'danger')
        else:
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            new_user = User(username=username, email=email, password_hash=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            flash(f'Utworzono nowego użytkownika: {username}', 'success')
        return redirect(url_for('admin.manage_users'))

    users = User.query.order_by(User.username).all()
    roles = Role.query.all()
    return render_template('manage_users.html', users=users, roles=roles)


@bp.route('/assign_roles/<int:user_id>', methods=['POST'])
@login_required
@permission_required('admin')
def assign_roles(user_id):
    user = User.query.get_or_404(user_id)
    
    submitted_role_ids = {int(id) for id in request.form.getlist('roles')}
    all_roles = Role.query.all()
    new_roles = []

    for role in all_roles:
        if role.id in submitted_role_ids:
            new_roles.append(role)
    
    if user.username == 'admin':
        admin_role = Role.query.filter_by(name='admin').first()
        if admin_role and admin_role not in new_roles:
            new_roles.append(admin_role)

    user.roles = new_roles
    db.session.commit()
    
    if user.id == current_user.id:
        login_user(user)
    
    flash(f"Zaktualizowano role dla użytkownika {user.username}.", "success")
    return redirect(url_for('admin.manage_users'))


@bp.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.username = request.form.get('username')
        user.email = request.form.get('email')
        db.session.commit()
        flash('Dane użytkownika zostały zaktualizowane.', 'success')
        return redirect(url_for('admin.manage_users'))
    return render_template('edit_user.html', user=user)


@bp.route('/change_password/<int:user_id>', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def change_password(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if new_password != confirm_password:
            flash('Hasła nie są identyczne.', 'danger')
        else:
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            user.password_hash = hashed_password
            db.session.commit()
            flash('Hasło zostało zmienione.', 'success')
            return redirect(url_for('admin.manage_users'))
    return render_template('change_password.html', user=user)

@bp.route('/tasks')
@login_required
@permission_required('admin')
def all_tasks():
    tasks = Task.query.order_by(Task.creation_date.desc()).all()
    return render_template('all_tasks.html', tasks=tasks)

@bp.route('/statistics')
@login_required
@permission_required('admin')
def statistics():
    engine_type = db.engine.dialect.name
    if engine_type == 'postgresql':
        date_func_daily = func.to_char(ProductionOrder.order_date, 'YYYY-MM-DD')
        date_func_weekly = func.to_char(ProductionOrder.order_date, 'YYYY-WW')
        date_func_monthly = func.to_char(ProductionOrder.order_date, 'YYYY-MM')
    else:
        date_func_daily = func.date(ProductionOrder.order_date)
        date_func_weekly = func.strftime('%Y-%W', ProductionOrder.order_date)
        date_func_monthly = func.strftime('%Y-%m', ProductionOrder.order_date)

    daily_stats = db.session.query(date_func_daily.label('date'), FinishedProduct.name.label('product_name'), func.sum(ProductionOrder.quantity_produced).label('total_quantity')).join(FinishedProduct).group_by('date', 'product_name').order_by(db.desc('date')).all()
    weekly_stats = db.session.query(date_func_weekly.label('week'), FinishedProduct.name.label('product_name'), func.sum(ProductionOrder.quantity_produced).label('total_quantity')).join(FinishedProduct).group_by('week', 'product_name').order_by(db.desc('week')).all()
    monthly_stats = db.session.query(date_func_monthly.label('month'), FinishedProduct.name.label('product_name'), func.sum(ProductionOrder.quantity_produced).label('total_quantity')).join(FinishedProduct).group_by('month', 'product_name').order_by(db.desc('month')).all()
    
    return render_template('statistics.html', daily_stats=daily_stats, weekly_stats=weekly_stats, monthly_stats=monthly_stats)

@bp.route('/activity_log')
@login_required
@permission_required('admin')
def activity_log():
    page = request.args.get('page', 1, type=int)
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).paginate(
        page=page, per_page=25
    )
    return render_template('activity_log.html', logs=logs)

@bp.route('/team_orders')
@login_required
@permission_required('admin')
def manage_team_orders():
    """Wyświetla listę zamówień od członków drużyny."""
    pending_orders = TeamOrder.query.filter_by(status='Oczekuje').order_by(TeamOrder.order_date.desc()).all()
    completed_orders = TeamOrder.query.filter_by(status='Zrealizowane').order_by(TeamOrder.order_date.desc()).limit(20).all()
    
    return render_template('manage_team_orders.html', 
                           pending_orders=pending_orders, 
                           completed_orders=completed_orders)


@bp.route('/team_orders/complete/<int:order_id>', methods=['POST'])
@login_required
@permission_required('admin')
def complete_team_order(order_id):
    """Oznacza zamówienie jako zrealizowane i zdejmuje produkty ze stanu."""
    order = TeamOrder.query.get_or_404(order_id)

    # 1. Sprawdź, czy zamówienie nie zostało już zrealizowane, aby uniknąć podwójnego zdjęcia ze stanu
    if order.status == 'Zrealizowane':
        flash(f"Zamówienie #{order.id} zostało już wcześniej zrealizowane.", 'warning')
        return redirect(url_for('admin.manage_team_orders'))

    # 2. Sprawdź, czy jest wystarczająca ilość produktów na stanie
    missing_products = []
    for item in order.products:
        product = item.product
        if product.quantity_in_stock < item.quantity:
            missing_products.append(f"'{product.name}' (brakuje: {item.quantity - product.quantity_in_stock} szt.)")
    
    if missing_products:
        error_message = "Nie można zrealizować zamówienia z powodu braków w magazynie: <ul>" + "".join(f"<li>{p}</li>" for p in missing_products) + "</ul>"
        flash(Markup(error_message), 'danger')
        return redirect(url_for('admin.manage_team_orders'))

    # 3. Odejmij produkty ze stanu magazynowego
    for item in order.products:
        item.product.quantity_in_stock -= item.quantity
    
    # 4. Zmień status zamówienia
    order.status = 'Zrealizowane'
    
    db.session.commit()
    
    log_activity(f"Zrealizował zamówienie drużynowe #{order.id} (dla {order.user.username}) i zdjął produkty ze stanu.")
    
    flash(f"Zamówienie #{order.id} zostało zrealizowane, a stany magazynowe zaktualizowane.", 'success')
    return redirect(url_for('admin.manage_team_orders'))