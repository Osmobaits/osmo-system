from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models import db, RawMaterial, Order, ProductionOrder, Task, VacationRequest

bp = Blueprint('main', __name__)

@bp.route('/')
@bp.route('/dashboard')
@login_required
def dashboard():
    # --- MODUŁ MAGAZYN ---
    # Znajdź wszystkie surowce, których łączny stan jest poniżej poziomu krytycznego
    low_stock_materials = []
    all_materials = RawMaterial.query.all()
    for material in all_materials:
        current_stock = sum(batch.quantity_on_hand for batch in material.batches)
        if material.critical_stock_level > 0 and current_stock < material.critical_stock_level:
            material.current_stock = current_stock  # Dodajemy atrybut pomocniczy
            low_stock_materials.append(material)

    # --- MODUŁ ZAMÓWIENIA ---
    active_orders = Order.query.filter_by(is_archived=False).order_by(Order.order_date.desc()).limit(5).all()
    orders_to_invoice = Order.query.filter_by(is_archived=True, invoice_number=None).order_by(Order.order_date.desc()).limit(5).all()

    # --- MODUŁ PRODUKCJA ---
    open_production_orders = ProductionOrder.query.filter(ProductionOrder.quantity_produced == 0).order_by(ProductionOrder.order_date.desc()).limit(5).all()

    # --- MODUŁ ZADANIA ---
    new_tasks_for_user = Task.query.filter(Task.assignees.contains(current_user), Task.status == 'Nowe').order_by(Task.creation_date.desc()).all()

    # --- MODUŁ URLOPY (tylko dla admina) ---
    pending_vacations = []
    if current_user.has_role('admin'):
        pending_vacations = VacationRequest.query.filter_by(status='Oczekuje').order_by(VacationRequest.request_date.asc()).all()

    return render_template(
        'dashboard.html',
        low_stock_materials=low_stock_materials,
        active_orders=active_orders,
        orders_to_invoice=orders_to_invoice,
        open_production_orders=open_production_orders,
        new_tasks_for_user=new_tasks_for_user,
        pending_vacations=pending_vacations
    )

# Ta trasa nie jest już potrzebna, bo /dashboard jest nową stroną główną
@bp.route('/home')
@login_required
def home():
    return redirect(url_for('main.dashboard'))