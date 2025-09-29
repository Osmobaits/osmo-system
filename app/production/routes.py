# app/production/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models import db, FinishedProduct, RawMaterial, RecipeComponent, ProductionOrder, RawMaterialBatch, ProductionLog, FinishedProductCategory, Packaging
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
        product_code = request.form.get('product_code')
        packaging_weight = request.form.get('packaging_weight', type=float)
        category_id = request.form.get('category_id', type=int)
        packaging_id = request.form.get('packaging_id', type=int)

        existing_by_name = FinishedProduct.query.filter_by(name=name).first()
        if existing_by_name:
            flash(f"Produkt o nazwie '{name}' już istnieje w katalogu.", "warning")
            return redirect(url_for('production.manage_catalogue'))

        if name and packaging_weight and category_id:
            new_product = FinishedProduct(
                name=name, 
                product_code=product_code, 
                packaging_weight_kg=packaging_weight, 
                category_id=category_id,
                packaging_id=packaging_id if packaging_id else None
            )
            db.session.add(new_product)
            db.session.commit()
            flash(f"Dodano produkt '{name}' do katalogu.", "success")
        return redirect(url_for('production.manage_catalogue'))
    
    # === POCZĄTEK ZMIANY ===
    # Pobieramy kategorie razem z przypisanymi produktami
    from sqlalchemy.orm import joinedload
    categories = FinishedProductCategory.query.options(
        joinedload(FinishedProductCategory.finished_products)
    ).order_by(FinishedProductCategory.name).all()
    all_packaging = Packaging.query.order_by(Packaging.name).all()
    # === KONIEC ZMIANY ===
    
    return render_template('manage_catalogue.html', categories=categories, all_packaging=all_packaging)

@bp.route('/catalogue/check_code')
@login_required
@permission_required('production')
def check_product_code():
    code = request.args.get('code', '', type=str)
    if not code:
        return jsonify({'exists': False})
    
    product = FinishedProduct.query.filter_by(product_code=code).first()
    return jsonify({'exists': product is not None})


@bp.route('/catalogue/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def edit_catalogue_product(id):
    product = FinishedProduct.query.get_or_404(id)
    product.name = request.form.get('name')
    product.product_code = request.form.get('product_code')
    product.packaging_weight_kg = request.form.get('packaging_weight', type=float)
    product.category_id = request.form.get('category_id', type=int)
    packaging_id = request.form.get('packaging_id', type=int)
    product.packaging_id = packaging_id if packaging_id else None
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
                planned_quantity=final_packaged_quantity,
                quantity_produced=0,
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
            
            db.session.commit()
            flash(f"Zlecenie na {final_packaged_quantity} opakowań '{product.name}' zostało utworzone. Uzupełnij rzeczywistą ilość w edycji.", "success")
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
    order = ProductionOrder.query.get_or_404(order_id)
    original_produced_quantity = order.quantity_produced

    if request.method == 'POST':
        new_produced_quantity = request.form.get('quantity', type=int)
        
        if new_produced_quantity is None or new_produced_quantity < 0:
            flash("Podano nieprawidłową ilość.", "danger")
            return redirect(url_for('production.edit_batch', order_id=order_id))
        
        try:
            quantity_difference = new_produced_quantity - original_produced_quantity
            
            if quantity_difference != 0:
                product = order.finished_product
                product.quantity_in_stock += quantity_difference

                if product.packaging:
                    product.packaging.quantity_in_stock -= quantity_difference

            order.quantity_produced = new_produced_quantity
            
            db.session.commit()
            flash(f"Zaktualizowano rzeczywistą ilość w partii.", "success")
            return redirect(url_for('production.manage_products'))
        except Exception as e:
            db.session.rollback()
            flash(f"Wystąpił błąd podczas edycji: {e}", "danger")
            return redirect(url_for('production.edit_batch', order_id=order_id))

    return render_template('edit_batch.html', batch=order)


@bp.route('/batch/delete/<int:order_id>', methods=['POST'])
@login_required
@permission_required('production')
def delete_batch(order_id):
    order = ProductionOrder.query.get_or_404(order_id)
    
    try:
        for log in order.consumption_log:
            batch = RawMaterialBatch.query.get(log.raw_material_batch_id)
            if batch:
                batch.quantity_on_hand += log.quantity_consumed
        
        product = order.finished_product
        product.quantity_in_stock -= order.quantity_produced
        
        if product.packaging:
            product.packaging.quantity_in_stock += order.quantity_produced
        
        ProductionLog.query.filter_by(production_order_id=order_id).delete()
        db.session.delete(order)
        db.session.commit()
        
        flash("Usunięto wpis z historii produkcji. Wszystkie surowce, produkty i opakowania zostały zwrócone na stan.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Wystąpił błąd podczas usuwania zlecenia: {e}", "danger")
        
    return redirect(url_for('production.manage_products'))

@bp.route('/order/<int:order_id>')
@login_required
@permission_required('production')
def production_order_details(order_id):
    order = ProductionOrder.query.get_or_404(order_id)
    from sqlalchemy.orm import joinedload
    consumption_logs = ProductionLog.query.options(
        joinedload(ProductionLog.batch).joinedload(RawMaterialBatch.material)
    ).filter_by(production_order_id=order_id).all()
    
    return render_template('production_order_details.html', order=order, logs=consumption_logs)