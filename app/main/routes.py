from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models import db, RawMaterial, Packaging, FinishedProduct, Order, ProductionOrder, Task, VacationRequest, TeamOrder

bp = Blueprint('main', __name__)

@bp.route('/')
@login_required
def index():
    return redirect(url_for('main.dashboard'))

@bp.route('/dashboard')
@login_required
def dashboard():
    # --- MAGAZYNY ---
    low_stock_materials = []
    all_materials = RawMaterial.query.all()
    for material in all_materials:
        current_stock = sum(batch.quantity_on_hand for batch in material.batches)
        if material.critical_stock_level > 0 and current_stock < material.critical_stock_level:
            material.current_stock = current_stock
            low_stock_materials.append(material)

    low_stock_packaging = Packaging.query.filter(Packaging.quantity_in_stock < Packaging.critical_stock_level, Packaging.critical_stock_level > 0).order_by(Packaging.name).all()
    low_stock_finished_products = FinishedProduct.query.filter(FinishedProduct.quantity_in_stock < FinishedProduct.critical_stock_level, FinishedProduct.critical_stock_level > 0).order_by(FinishedProduct.name).all()

    # --- ZAMÓWIENIA ---
    active_orders = Order.query.filter_by(is_archived=False).order_by(Order.order_date.desc()).limit(5).all()
    orders_to_invoice = Order.query.filter_by(is_archived=True, invoice_number=None).order_by(Order.order_date.desc()).limit(5).all()

    # --- PRODUKCJA ---
    open_production_orders = ProductionOrder.query.filter(ProductionOrder.quantity_produced == 0).order_by(ProductionOrder.order_date.desc()).limit(5).all()

    # --- ZADANIA ---
    new_tasks_for_user = Task.query.filter(Task.assignees.contains(current_user), Task.status == 'Nowe').order_by(Task.creation_date.desc()).all()

    # --- SEKCJE TYLKO DLA ADMINA ---
    pending_vacations = []
    pending_team_orders = [] # Inicjalizujemy pustą listę
    if current_user.has_role('admin'):
        pending_vacations = VacationRequest.query.filter_by(status='Oczekuje').order_by(VacationRequest.request_date.asc()).all()
        # --- NOWA LOGIKA ---
        pending_team_orders = TeamOrder.query.filter_by(status='Oczekuje').order_by(TeamOrder.order_date.desc()).all()
        # -------------------

    return render_template(
        'dashboard.html',
        low_stock_materials=low_stock_materials,
        low_stock_packaging=low_stock_packaging,
        low_stock_finished_products=low_stock_finished_products,
        active_orders=active_orders,
        orders_to_invoice=orders_to_invoice,
        open_production_orders=open_production_orders,
        new_tasks_for_user=new_tasks_for_user,
        pending_vacations=pending_vacations,
        pending_team_orders=pending_team_orders # <-- Przekazanie do widoku
    )