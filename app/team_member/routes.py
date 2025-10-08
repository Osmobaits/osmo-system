from flask import Blueprint, render_template, request, redirect, url_for, flash
# Zaktualizuj tę linię, aby zawierała brakujące importy
from app.models import db, Task, TeamOrder, TeamOrderProduct, FinishedProduct, FinishedProductCategory 
from flask_login import login_required, current_user
from app.decorators import permission_required
from app.utils import log_activity
from sqlalchemy import desc
from functools import wraps

bp = Blueprint('team_member', __name__, template_folder='templates', url_prefix='/team')

def team_member_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not (current_user.has_role('team_member') or current_user.has_role('admin')):
            flash('Brak uprawnień do dostępu do tej strony.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/dashboard')
@login_required
@team_member_required
def dashboard():
    my_tasks = Task.query.filter(Task.assignees.contains(current_user), Task.status != 'Zakończone').order_by(Task.creation_date.desc()).all()
    my_orders = TeamOrder.query.filter_by(user_id=current_user.id).order_by(desc(TeamOrder.order_date)).limit(5).all()
    
    return render_template('team_dashboard.html', 
                           tasks=my_tasks, 
                           orders=my_orders)

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
    team_categories = FinishedProductCategory.query.filter_by(available_for_team=True).order_by(FinishedProductCategory.name).all()
    
    if request.method == 'POST':
        notes = request.form.get('notes')
        new_team_order = TeamOrder(user_id=current_user.id, notes=notes)
        db.session.add(new_team_order)
        
        has_items = False
        available_products = FinishedProduct.query.filter(FinishedProduct.category_id.in_([c.id for c in team_categories])).all()
        
        for product in available_products:
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
        
    return render_template('new_team_order.html', categories=team_categories)

@bp.route('/order_history')
@login_required
@team_member_required
def order_history():
    my_orders = TeamOrder.query.filter_by(user_id=current_user.id).order_by(desc(TeamOrder.order_date)).all()
    return render_template('team_order_history.html', orders=my_orders)
    
@bp.route('/order/<int:order_id>', methods=['GET', 'POST'])
@login_required
@team_member_required
def edit_my_order(order_id):
    order = TeamOrder.query.get_or_404(order_id)

    # Sprawdź, czy użytkownik jest właścicielem zamówienia i czy jest ono wciąż otwarte
    if order.user_id != current_user.id:
        flash('Nie masz uprawnień do edycji tego zamówienia.', 'danger')
        return redirect(url_for('team_member.dashboard'))
    if order.status != 'Oczekuje':
        flash('Nie można edytować zamówienia, które zostało już zrealizowane.', 'warning')
        return redirect(url_for('team_member.order_history'))

    if request.method == 'POST':
        order.notes = request.form.get('notes')
        
        # Stwórz słownik z istniejącymi produktami w zamówieniu dla łatwej aktualizacji
        existing_products = {item.product_id: item for item in order.products}

        team_categories = FinishedProductCategory.query.filter_by(available_for_team=True).all()
        available_products = FinishedProduct.query.filter(FinishedProduct.category_id.in_([c.id for c in team_categories])).all()

        for product in available_products:
            quantity = request.form.get(f'product_{product.id}', type=int)
            
            # Sprawdź, czy produkt był już w zamówieniu
            existing_item = existing_products.get(product.id)

            if quantity and quantity > 0:
                if existing_item:
                    # Aktualizuj istniejący
                    existing_item.quantity = quantity
                else:
                    # Dodaj nowy
                    new_item = TeamOrderProduct(order=order, product_id=product.id, quantity=quantity)
                    db.session.add(new_item)
            elif existing_item:
                # Jeśli ilość to 0, a produkt istniał - usuń go
                db.session.delete(existing_item)
        
        db.session.commit()
        log_activity(f"Zmodyfikował swoje zamówienie drużynowe #{order.id}")
        flash('Zamówienie zostało zaktualizowane.', 'success')
        return redirect(url_for('team_member.order_history'))

    # Przygotuj słownik z ilościami dla formularza
    order_quantities = {item.product_id: item.quantity for item in order.products}
    team_categories = FinishedProductCategory.query.filter_by(available_for_team=True).order_by(FinishedProductCategory.name).all()
    
    return render_template('edit_team_order.html', order=order, categories=team_categories, quantities=order_quantities)