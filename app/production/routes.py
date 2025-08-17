# app/production/routes.py
import math
from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
from app.models import db, FinishedProduct, RawMaterial, RecipeComponent, ProductionOrder
from flask_login import login_required
from app.decorators import permission_required

bp = Blueprint('production', __name__, template_folder='templates', url_prefix='/production')

@bp.route('/products') # URL pozostaje ten sam dla spójności
@login_required
@permission_required('production')
def manage_products():
    # Pobieramy całą historię produkcji posortowaną od najnowszej
    production_history = ProductionOrder.query.order_by(ProductionOrder.order_date.desc()).all()
    
    return render_template('manage_finished_products.html', production_history=production_history)

@bp.route('/products/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def edit_product(id):
    product = FinishedProduct.query.get_or_404(id)
    new_name = request.form.get('name')
    new_weight = request.form.get('packaging_weight')
    if new_name and new_weight:
        product.name = new_name
        product.packaging_weight_kg = float(new_weight)
        db.session.commit()
        flash("Dane produktu zostały zaktualizowane.", "success")
    return redirect(url_for('production.manage_products'))

@bp.route('/products/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def delete_product(id):
    product = FinishedProduct.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash(f"Produkt '{product.name}' został usunięty.", "danger")
    return redirect(url_for('production.manage_products'))

@bp.route('/products/<int:id>/recipe', methods=['GET', 'POST'])
@login_required
@permission_required('production')
def manage_recipe(id):
    product = FinishedProduct.query.get_or_404(id)
    if request.method == 'POST':
        raw_material_id = request.form.get('raw_material_id')
        quantity = request.form.get('quantity')
        if raw_material_id and quantity:
            existing_comp = RecipeComponent.query.filter_by(finished_product_id=id, raw_material_id=raw_material_id).first()
            if not existing_comp:
                new_component = RecipeComponent(finished_product_id=id, raw_material_id=int(raw_material_id), quantity_required=float(quantity))
                db.session.add(new_component)
                db.session.commit()
                flash("Dodano składnik do receptury.", "success")
            else:
                flash("Ten surowiec już jest w recepturze. Możesz edytować jego ilość.", "warning")
        return redirect(url_for('production.manage_recipe', id=id))
    all_raw_materials = RawMaterial.query.order_by(RawMaterial.name).all()
    return render_template('manage_recipe.html', product=product, raw_materials=all_raw_materials)

@bp.route('/recipe/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def edit_recipe_component(id):
    component = RecipeComponent.query.get_or_404(id)
    new_quantity = request.form.get('quantity')
    if new_quantity:
        component.quantity_required = float(new_quantity)
        db.session.commit()
        flash("Zaktualizowano ilość składnika.", "success")
    return redirect(url_for('production.manage_recipe', id=component.finished_product_id))

@bp.route('/recipe/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def delete_recipe_component(id):
    component = RecipeComponent.query.get_or_404(id)
    product_id_redirect = component.finished_product_id
    db.session.delete(component)
    db.session.commit()
    flash("Usunięto składnik z receptury.", "danger")
    return redirect(url_for('production.manage_recipe', id=product_id_redirect))

@bp.route('/orders', methods=['GET', 'POST'])
@login_required
@permission_required('production')
def manage_production_orders():
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        batch_size = request.form.get('batch_size')
        if not product_id or not batch_size or int(batch_size) <= 0:
            flash("Wybierz produkt i podaj prawidłową liczbę porcji.", "warning")
            return redirect(url_for('production.manage_production_orders'))
        batch_size = int(batch_size)
        product = FinishedProduct.query.get_or_404(product_id)
        if not product.recipe_components:
            flash(f"Produkt '{product.name}' nie ma zdefiniowanej receptury!", "danger")
            return redirect(url_for('production.manage_production_orders'))
        total_produced_weight = 0
        can_produce = True
        needed_materials = []
        for component in product.recipe_components:
            required_qty = component.quantity_required * batch_size
            total_produced_weight += required_qty
            if component.raw_material.quantity_in_stock < required_qty:
                flash(f"Brak surowca: {component.raw_material.name}. Potrzeba {required_qty}, jest {component.raw_material.quantity_in_stock}.", "danger")
                can_produce = False
            needed_materials.append({'material': component.raw_material, 'qty': required_qty})
        if product.packaging_weight_kg > 0:
            final_packaged_quantity = math.floor(total_produced_weight / product.packaging_weight_kg)
        else:
            final_packaged_quantity = 0
            flash("Waga opakowania musi być większa od zera!", "danger")
            can_produce = False
        if final_packaged_quantity == 0 and can_produce:
             flash(f"Całkowita waga wsadu ({total_produced_weight} kg) jest mniejsza niż waga jednego opakowania ({product.packaging_weight_kg} kg).", "warning")
             can_produce = False
        if can_produce:
            try:
                for item in needed_materials:
                    item['material'].quantity_in_stock -= item['qty']
                product.quantity_in_stock += final_packaged_quantity
                new_order = ProductionOrder(finished_product_id=product.id, quantity_produced=final_packaged_quantity)
                db.session.add(new_order)
                db.session.commit()
                flash(f"Wyprodukowano {final_packaged_quantity} szt. produktu {product.name} (waga wsadu: {total_produced_weight} kg).", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Wystąpił błąd: {e}", "danger")
        return redirect(url_for('production.manage_production_orders'))
    all_finished_products = FinishedProduct.query.order_by(FinishedProduct.name).all()
    all_production_orders = ProductionOrder.query.order_by(ProductionOrder.order_date.desc()).all()
    return render_template('production_orders.html', products=all_finished_products, orders=all_production_orders)
    
@bp.route('/edit_batch/<int:order_id>', methods=['GET', 'POST'])
@login_required
@permission_required('production')
def edit_batch(order_id):
    batch = ProductionOrder.query.get_or_404(order_id)
    if request.method == 'POST':
        new_quantity = int(request.form.get('quantity'))
        
        # Prosta walidacja, aby nie wprowadzić ujemnej wartości
        if new_quantity >= 0:
            batch.quantity_produced = new_quantity
            db.session.commit()
            flash("Zaktualizowano ilość w partii produkcyjnej.", "success")
            return redirect(url_for('production.manage_products'))
        else:
            flash("Ilość nie może być ujemna.", "danger")

    return render_template('edit_batch.html', batch=batch)


@bp.route('/delete_batch/<int:order_id>', methods=['POST'])
@login_required
@permission_required('production')
def delete_batch(order_id):
    batch_to_delete = ProductionOrder.query.get_or_404(order_id)
    db.session.delete(batch_to_delete)
    db.session.commit()
    flash("Partia produkcyjna została usunięta z historii.", "danger")
    return redirect(url_for('production.manage_products'))
    
@bp.route('/catalogue', methods=['GET', 'POST'])
@login_required
@permission_required('production')
def manage_catalogue():
    if request.method == 'POST':
        product_name = request.form.get('name')
        packaging_weight = request.form.get('packaging_weight')
        if product_name and packaging_weight:
            existing_product = FinishedProduct.query.filter_by(name=product_name).first()
            if not existing_product:
                new_product = FinishedProduct(name=product_name, packaging_weight_kg=float(packaging_weight))
                db.session.add(new_product)
                db.session.commit()
                flash(f"Dodano produkt do katalogu: {product_name}", "success")
            else:
                flash("Produkt o tej nazwie już istnieje w katalogu.", "warning")
        return redirect(url_for('production.manage_catalogue'))

    all_products = FinishedProduct.query.order_by(FinishedProduct.name).all()
    return render_template('manage_catalogue.html', products=all_products)

@bp.route('/catalogue/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def edit_catalogue_product(id):
    product = FinishedProduct.query.get_or_404(id)
    new_name = request.form.get('name')
    new_weight = request.form.get('packaging_weight')
    if new_name and new_weight:
        product.name = new_name
        product.packaging_weight_kg = float(new_weight)
        db.session.commit()
        flash("Dane produktu zostały zaktualizowane.", "success")
    return redirect(url_for('production.manage_catalogue'))