from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, Task, TeamOrder, TeamOrderProduct, FinishedProduct
from flask_login import login_required, current_user
from app.decorators import permission_required
from app.utils import log_activity
from sqlalchemy import desc
from functools import wraps

bp = Blueprint('team_member', __name__, template_folder='templates', url_prefix='/team')

def team_member_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Tymczasowo wyłączamy to zabezpieczenie, aby admin mógł wejść
        # if not current_user.has_role('team_member'):
        #     flash('Brak uprawnień do dostępu do tej strony.', 'danger')
        #     return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/dashboard')
@login_required
@team_member_required
def dashboard():
    my_tasks = Task.query.filter(Task.assignees.contains(current_user), Task.status != 'Zakończone').order_by(Task.creation_date.desc()).all()
    my_orders = TeamOrder.query.filter_by(user_id=current_user.id).order_by(desc(TeamOrder.order_date)).limit(5).all()
    
    # --- ZMIENNA DIAGNOSTYCZNA ---
    all_user_roles = [role.name for role in current_user.roles]
    # ------------------------------------

    return render_template('team_dashboard.html', 
                           tasks=my_tasks, 
                           orders=my_orders,
                           all_user_roles=all_user_roles) # Przekazujemy role do widoku

@bp.route('/my_profile', methods=['GET', 'POST'])
@login_required
@team_member_required
def my_profile():
    if request.method == 'POST':
        current_user.address_street = request.form.get('address_street')
        current_user.address_postal_code = request.form.get('address_postal_code')
        current_user.address_city = request.form.get('address_city')
        current_user.phone_number = request.form.get('phone_number')
        db.session.commit()
        
        log_activity("Zaktualizował swój adres do wysyłki.")
        
        flash('Twój profil został zaktualizowany.', 'success')
        return redirect(url_for('team_member.my_profile'))
    return render_template('my_profile.html')

@bp.route('/new_order', methods=['GET', 'POST'])
@login_required
@team_member_required
def new_order():
    if request.method == 'POST':
        notes = request.form.get('notes')
        
        new_team_order = TeamOrder(user_id=current_user.id, notes=notes)
        db.session.add(new_team_order)
        
        has_items = False
        for product in FinishedProduct.query.all():
            quantity = request.form.get(f'product_{product.id}', type=int)
            if quantity and quantity > 0:
                order_item = TeamOrderProduct(order=new_team_order, product_id=product.id, quantity=quantity)
                db.session.add(order_item)
                has_items = True

        if not has_items:
            flash('Twoje zamówienie jest puste. Dodaj przynajmniej jeden produkt.', 'warning')
            return redirect(url_for('team_member.new_order'))

        db.session.commit()
        log_activity(f"Złożył nowe zamówienie drużynowe #{new_team_order.id}")
        flash('Twoje zamówienie zostało złożone pomyślnie!', 'success')
        return redirect(url_for('team_member.dashboard'))
        
    products = FinishedProduct.query.order_by(FinishedProduct.name).all()
    return render_template('new_team_order.html', products=products)

@bp.route('/order_history')
@login_required
@team_member_required
def order_history():
    my_orders = TeamOrder.query.filter_by(user_id=current_user.id).order_by(desc(TeamOrder.order_date)).all()
    return render_template('team_order_history.html', orders=my_orders)