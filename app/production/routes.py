# app/production/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, FinishedProduct, RawMaterial, RecipeComponent, ProductionOrder, RawMaterialBatch, ProductionLog
from flask_login import login_required
from app.decorators import permission_required
import math

bp = Blueprint('production', __name__, template_folder='templates', url_prefix='/production')

@bp.route('/products')
@login_required
@permission_required('production')
def manage_products():
    production_history = ProductionOrder.query.order_by(ProductionOrder.order_date.desc()).all()
    return render_template('manage_finished_products.html', production_history=production_history)


@bp.route('/catalogue', methods=['GET', 'POST'])
@login_required
@permission_required('production')
def manage_catalogue():
    if request.method == 'POST':
        name = request.form.get('name')
        packaging_weight = request.form.get('packaging_weight', type=float)
        
        existing = FinishedProduct.query.filter_by(name=name).first()
        if existing:
            flash(f"Produkt o nazwie '{name}' już istnieje w katalogu.", "warning")
            return redirect(url_for('production.manage_catalogue'))

        if name and packaging_weight:
            new_product = FinishedProduct(name=name, packaging_weight_kg=packaging_weight)
            db.session.add(new_product)
            db.session.commit()
            flash(f"Dodano produkt '{name}' do katalogu.", "success")
        return redirect(url_for('production.manage_catalogue'))
    
    products = FinishedProduct.query.order_by(FinishedProduct.name).all()
    return render_template('manage_catalogue.html', products=products)

@bp.route('/catalogue/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def edit_catalogue_product(id):
    product = FinishedProduct.query.get_or_404(id)
    product.name = request.form.get('name')
    product.packaging_weight_kg = request.form.get('packaging_weight', type=float)
    db.session.commit()
    flash("Zapisano zmiany w produkcie.", "success")
    return redirect(url_for('production.manage_catalogue'))


@bp.route('/products/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def delete_product(id):
    product = FinishedProduct.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash(f"Produkt '{product.name}' i jego historia produkcji zostały usunięte.", "danger")
    return redirect(url_for('production.manage_catalogue'))


@bp.route('/products/<int:id>/recipe', methods=['GET', 'POST'])
@login_required
@permission_required('production')
def manage_recipe(id):
    product = FinishedProduct.query.get_or_404(id)
    if request.method == 'POST':
        raw_material_id = request.form.get('raw_material_id', type=int)
        quantity = request.form.get('quantity', type=float)

        existing_component = RecipeComponent.query.filter_by(finished_product_id=id, raw_material_id=raw_material_id).first()
        if existing_component:
            flash("Ten surowiec już jest w recepturze. Możesz edytować jego ilość.", "warning")
        elif raw_material_id and quantity:
            new_component = RecipeComponent(finished_product_id=id, raw_material_id=raw_material_id, quantity_required=quantity)
            db.session.add(new_component)
            db.session.commit()
            flash("Dodano składnik do receptury.", "success")
        return redirect(url_for('production.manage_recipe', id=id))
    
    raw_materials = RawMaterial.query.order_by(RawMaterial.name).all()
    return render_template('manage_recipe.html', product=product, raw_materials=raw_materials)

@bp.route('/recipe/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def edit_recipe_component(id):
    component = RecipeComponent.query.get_or_404(id)
    component.quantity_required = request.form.get('quantity', type=float)
    db.session.commit()
    flash("Zaktualizowano ilość składnika.", "success")
    return redirect(url_for('production.manage_recipe', id=component.finished_product_id))

@bp.route('/recipe/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def delete_recipe_component(id):
    component = RecipeComponent.query.get_or_404(id)
    product_id = component.finished_product_id
    db.session.delete(component)
    db.session.commit()
    flash("Usunięto składnik z receptury.", "danger")
    return redirect(url_for('production.manage_recipe', id=product_id))


@bp.route('/orders', methods=['GET', 'POST'])
@login_required
@permission_required('production')
def manage_production_orders():
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        batch_size = request.form.get('batch_size', type=int)

        if not product_id or not batch_size or batch_size <= 0:
            flash("Proszę wybrać produkt i podać prawidłową liczbę porcji.", "warning")
            return redirect(url_for('production.manage_production_orders'))

        product = FinishedProduct.query.get_or_404(product_id)
        if not product.recipe_components:
            flash(f"Produkt '{product.name}' nie ma zdefiniowanej receptury. Produkcja niemożliwa.", "danger")
            return redirect(url_for('production.manage_production_orders'))

        consumption_plan = []
        can_produce = True
        total_produced_weight = 0.0
        
        for component in product.recipe_components:
            required_quantity = component.quantity_required * batch_size
            total_produced_weight += required_quantity
            
            available_batches = RawMaterialBatch.query.filter_by(raw_material_id=component.raw_material_id)\
                                                      .filter(RawMaterialBatch.quantity_on_hand > 0)\
                                                      .order_by(RawMaterialBatch.received_date).all()
            
            temp_required = required_quantity
            for batch in available_batches:
                if temp_required <= 0: break
                
                quantity_to_take = min(temp_required, batch.quantity_on_hand)
                consumption_plan.append({
                    'batch_id': batch.id,
                    'consumed_quantity': quantity_to_take
                })
                temp_required -= quantity_to_take
            
            if temp_required > 0.001:
                unit = ""
                if available_batches:
                    unit = available_batches[0].unit
                elif component.raw_material.batches:
                    unit = component.raw_material.batches[0].unit
                
                flash(f"Niewystarczająca ilość surowca: {component.raw_material.name}. Brakuje {temp_required:.2f} {unit}.", "danger")
                can_produce = False
                break
        
        if not can_produce:
            return redirect(url_for('production.manage_production_orders'))

        sample_needed = False
        last_order = ProductionOrder.query.filter_by(finished_product_id=product.id).order_by(ProductionOrder.order_date.desc()).first()
        
        if not last_order:
            sample_needed = True
        else:
            previous_batches_ids = {log.raw_material_batch_id for log in last_order.consumption_log}
            current_batches_ids = {plan['batch_id'] for plan in consumption_plan}
            if previous_batches_ids != current_batches_ids:
                sample_needed = True

        if product.packaging_weight_kg > 0:
            final_packaged_quantity = math.floor(total_produced_weight / product.packaging_weight_kg)
        else:
            final_packaged_quantity = 0

        if final_packaged_quantity <= 0:
            flash("Wyprodukowana ilość jest zbyt mała, aby stworzyć chociaż jedno opakowanie produktu.", "warning")
            return redirect(url_for('production.manage_production_orders'))

        try:
            new_order = ProductionOrder(
                finished_product_id=product.id,
                quantity_produced=final_packaged_quantity,
                sample_required=sample_needed
            )
            db.session.add(new_order)
            db.session.flush()

            for plan_item in consumption_plan:
                batch_to_update = RawMaterialBatch.query.get(plan_item['batch_id'])
                batch_to_update.quantity_on_hand -= plan_item['consumed_quantity']
                
                log_entry = ProductionLog(
                    production_order_id=new_order.id,
                    raw_material_batch_id=batch_to_update.id,
                    quantity_consumed=plan_item['consumed_quantity']
                )
                db.session.add(log_entry)
            
            product.quantity_in_stock += final_packaged_quantity
            
            db.session.commit()
            flash(f"Wyprodukowano {final_packaged_quantity} opakowań produktu '{product.name}'.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Wystąpił błąd podczas produkcji: {e}", "danger")
            
        return redirect(url_for('production.manage_production_orders'))

    products = FinishedProduct.query.order_by(FinishedProduct.name).all()
    orders = ProductionOrder.query.order_by(ProductionOrder.order_date.desc()).limit(20).all()
    return render_template('production_orders.html', products=products, orders=orders)


@bp.route('/batch/edit/<int:order_id>', methods=['GET', 'POST'])
@login_required
@permission_required('production')
def edit_batch(order_id):
    batch = ProductionOrder.query.get_or_404(order_id)
    if request.method == 'POST':
        batch.quantity_produced = request.form.get('quantity', type=int)
        db.session.commit()
        flash("Zaktualizowano ilość w partii produkcyjnej.", "success")
        return redirect(url_for('production.manage_products'))
    return render_template('edit_batch.html', batch=batch)


@bp.route('/batch/delete/<int:order_id>', methods=['POST'])
@login_required
@permission_required('production')
def delete_batch(order_id):
    batch = ProductionOrder.query.get_or_404(order_id)
    db.session.delete(batch)
    db.session.commit()
    flash("Usunięto wpis z historii produkcji.", "danger")
    return redirect(url_for('production.manage_products'))

# === POCZĄTEK NOWEJ FUNKCJI ===
@bp.route('/order/<int:order_id>')
@login_required
@permission_required('production')
def production_order_details(order_id):
    order = ProductionOrder.query.get_or_404(order_id)
    # Używamy .options(joinedload(...)) dla optymalizacji, aby uniknąć wielu zapytań do bazy w pętli
    from sqlalchemy.orm import joinedload
    consumption_logs = ProductionLog.query.options(
        joinedload(ProductionLog.batch).joinedload(RawMaterialBatch.material)
    ).filter_by(production_order_id=order_id).all()
    
    return render_template('production_order_details.html', order=order, logs=consumption_logs)
# === KONIEC NOWEJ FUNKCJI ===