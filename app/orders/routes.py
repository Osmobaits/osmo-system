# app/orders/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models import db, Client, Order, OrderProduct, ClientProduct
from datetime import datetime
from flask_login import login_required
from app.decorators import permission_required

bp = Blueprint('orders', __name__, template_folder='templates', url_prefix='/orders')

@bp.route('/clients', methods=['GET', 'POST'])
@login_required
@permission_required('orders')
def manage_clients():
    if request.method == 'POST':
        client_name = request.form.get('name')
        if client_name:
            existing_client = Client.query.filter_by(name=client_name).first()
            if not existing_client:
                new_client = Client(name=client_name)
                db.session.add(new_client)
                db.session.commit()
                flash(f"Dodano klienta: {client_name}", "success")
            else:
                flash("Klient o tej nazwie już istnieje.", "warning")
        return redirect(url_for('orders.manage_clients'))

    all_clients = Client.query.order_by(Client.name).all()
    active_orders = Order.query.filter_by(is_archived=False).order_by(Order.order_date.desc()).all()
    
    # === NOWA LOGIKA: POBIERANIE ZAMÓWIEŃ DO ZAFAKTUROWANIA ===
    orders_to_invoice = Order.query.filter(
        Order.is_archived == True,
        db.or_(Order.invoice_number == None, Order.invoice_number == '')
    ).order_by(Order.order_date.asc()).all()
    
    return render_template(
        'manage_clients.html', 
        clients=all_clients, 
        active_orders=active_orders, 
        orders_to_invoice=orders_to_invoice # Przekazujemy nową listę do szablonu
    )

@bp.route('/clients/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('orders')
def edit_client(id):
    client = Client.query.get_or_404(id)
    new_name = request.form.get('name')
    if new_name:
        client.name = new_name
        db.session.commit()
        flash("Nazwa klienta została zaktualizowana.", "success")
    return redirect(url_for('orders.manage_clients'))

@bp.route('/clients/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('orders')
def delete_client(id):
    client = Client.query.get_or_404(id)
    db.session.delete(client)
    db.session.commit()
    flash(f"Klient '{client.name}' został usunięty.", "danger")
    return redirect(url_for('orders.manage_clients'))

@bp.route('/client/<int:id>')
@login_required
@permission_required('orders')
def client_details(id):
    client = Client.query.get_or_404(id)
    return render_template('client_details.html', client=client)

@bp.route('/client/<int:id>/add_product', methods=['POST'])
@login_required
@permission_required('orders')
def add_client_product(id):
    product_name = request.form.get('product_name')
    if product_name:
        existing = ClientProduct.query.filter_by(client_id=id, product_name=product_name).first()
        if not existing:
            new_product = ClientProduct(client_id=id, product_name=product_name)
            db.session.add(new_product)
            db.session.commit()
            flash(f"Dodano produkt '{product_name}' do katalogu klienta.", "success")
        else:
            flash("Klient ma już produkt o tej nazwie w swoim katalogu.", "warning")
    return redirect(url_for('orders.client_details', id=id))

@bp.route('/client/delete_product/<int:id>', methods=['POST'])
@login_required
@permission_required('orders')
def delete_client_product(id):
    product_to_delete = ClientProduct.query.get_or_404(id)
    client_id_redirect = product_to_delete.client_id
    db.session.delete(product_to_delete)
    db.session.commit()
    flash("Usunięto produkt z katalogu klienta.", "danger")
    return redirect(url_for('orders.client_details', id=client_id_redirect))

@bp.route('/client/<int:id>/add_order', methods=['POST'])
@login_required
@permission_required('orders')
def add_order(id):
    new_order = Order(client_id=id)
    db.session.add(new_order)
    db.session.commit()
    flash("Utworzono nowe zamówienie.", "success")
    return redirect(url_for('orders.order_details', id=new_order.id))

@bp.route('/order/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('orders')
def order_details(id):
    order = Order.query.get_or_404(id)
    if request.method == 'POST':
        client_product_id = request.form.get('client_product_id')
        quantity = request.form.get('quantity')
        if client_product_id and quantity and int(quantity) > 0:
            product = ClientProduct.query.get(client_product_id)
            new_order_product = OrderProduct(order_id=id, product_name=product.product_name, quantity_ordered=int(quantity))
            db.session.add(new_order_product)
            db.session.commit()
            flash(f"Dodano '{product.product_name}' do zamówienia.", "success")
        else:
            flash("Wybierz produkt i podaj poprawną ilość.", "warning")
        return redirect(url_for('orders.order_details', id=id))
    client_products = ClientProduct.query.filter_by(client_id=order.client_id).order_by(ClientProduct.product_name).all()
    return render_template('order_details.html', order=order, client_products=client_products)

@bp.route('/order/delete_product/<int:id>', methods=['POST'])
@login_required
@permission_required('orders')
def delete_order_product(id):
    order_product = OrderProduct.query.get_or_404(id)
    order_id_redirect = order_product.order_id
    db.session.delete(order_product)
    db.session.commit()
    flash("Usunięto produkt z zamówienia.", "warning")
    return redirect(url_for('orders.order_details', id=order_id_redirect))

@bp.route('/order/update_product_quantity/<int:id>', methods=['POST'])
@login_required
@permission_required('orders')
def update_order_product_quantity(id):
    order_product = OrderProduct.query.get_or_404(id)
    data = request.json
    if 'quantity_packed' in data:
        order_product.quantity_packed = int(data['quantity_packed'])
    elif 'quantity_wykulane' in data:
        order_product.quantity_wykulane = int(data['quantity_wykulane'])
    try:
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/order/archive/<int:id>', methods=['POST'])
@login_required
@permission_required('orders')
def archive_order(id):
    order = Order.query.get_or_404(id)
    invoice_number = request.form.get('invoice_number')
    
    # Ustawiamy status na zarchiwizowany (nic się nie stanie, jeśli już jest)
    order.is_archived = True
    
    # Aktualizujemy lub dodajemy numer faktury
    order.invoice_number = invoice_number if invoice_number else None
    
    db.session.commit()
    flash("Zamówienie zostało zaktualizowane i zarchiwizowane.", "success")
    
    # Przekierowujemy z powrotem na pulpit, aby zobaczyć efekt na listach
    return redirect(url_for('orders.manage_clients'))

@bp.route('/order/delete_archived/<int:id>', methods=['POST'])
@login_required
@permission_required('orders')
def delete_archived_order(id):
    order_to_delete = Order.query.get_or_404(id)
    client_id_redirect = order_to_delete.client_id
    if order_to_delete.is_archived:
        db.session.delete(order_to_delete)
        db.session.commit()
        flash("Zarchiwizowane zamówienie zostało trwale usunięte.", "danger")
    else:
        flash("Nie można usunąć aktywnego zamówienia.", "warning")
    return redirect(url_for('orders.client_details', id=client_id_redirect))