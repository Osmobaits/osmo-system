# app/production/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models import db, FinishedProduct, RawMaterial, RecipeComponent, ProductionOrder, RawMaterialBatch, ProductionLog, FinishedProductCategory, Packaging, ProductPackaging
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
        unit = request.form.get('unit')
        category_id = request.form.get('category_id', type=int)
        
        existing_by_name = FinishedProduct.query.filter_by(name=name).first()
        if existing_by_name:
            flash(f"Produkt o nazwie '{name}' już istnieje w katalogu.", "warning")
            return redirect(url_for('production.manage_catalogue'))

        if name and packaging_weight and category_id and unit:
            new_product = FinishedProduct(
                name=name, 
                product_code=product_code, 
                packaging_weight_kg=packaging_weight, 
                unit=unit,
                category_id=category_id
            )
            db.session.add(new_product)
            db.session.commit()
            flash(f"Dodano produkt '{name}' do katalogu.", "success")
        return redirect(url_for('production.manage_catalogue'))
    
    from sqlalchemy.orm import joinedload
    categories = FinishedProductCategory.query.options(
        joinedload(FinishedProductCategory.finished_products)
    ).order_by(FinishedProductCategory.name).all()
    
    return render_template('manage_catalogue.html', categories=categories)

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
    product.unit = request.form.get('unit')
    product.category_id = request.form.get('category_id', type=int)
    db.session.commit()
    flash("Zapisano zmiany w produkcie.", "success")
    return redirect(url_for('production.manage_catalogue'))


@bp.route('/products/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def delete_product(id):
    product = FinishedProduct.query.get_or_404(id)
    usage_in_recipe = RecipeComponent.query.filter_by(sub_product_id=id).first()
    if usage_in_recipe:
        flash(f"Nie można usunąć produktu '{product.name}', ponieważ jest on używany jako PÓŁPRODUKT w recepturze produktu '{usage_in_recipe.product.name}'.", "danger")
        return redirect(url_for('production.manage_catalogue'))

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
        component_type = request.form.get('component_type')
        quantity = request.form.get('quantity', type=float)
        unit = request.form.get('unit')
        
        if not component_type or not quantity or quantity <= 0 or not unit:
            flash("Wybierz składnik, jednostkę i podaj prawidłową ilość.", "danger")
            return redirect(url_for('production.manage_recipe', id=id))

        if component_type == 'raw_material':
            raw_material_id = request.form.get('raw_material_id', type=int)
            if not raw_material_id:
                flash("Wybierz surowiec.", "danger")
                return redirect(url_for('production.manage_recipe', id=id))
            
            existing = RecipeComponent.query.filter_by(finished_product_id=id, raw_material_id=raw_material_id).first()
            if existing:
                flash("Ten surowiec już jest w recepturze.", "warning")
            else:
                new_component = RecipeComponent(finished_product_id=id, raw_material_id=raw_material_id, quantity_required=quantity, unit=unit)
                db.session.add(new_component)
                db.session.commit()
                flash("Dodano surowiec do receptury.", "success")

        elif component_type == 'sub_product':
            sub_product_id = request.form.get('sub_product_id', type=int)
            if not sub_product_id:
                flash("Wybierz półprodukt.", "danger")
                return redirect(url_for('production.manage_recipe', id=id))
            
            existing = RecipeComponent.query.filter_by(finished_product_id=id, sub_product_id=sub_product_id).first()
            if existing:
                flash("Ten półprodukt już jest w recepturze.", "warning")
            else:
                new_component = RecipeComponent(finished_product_id=id, sub_product_id=sub_product_id, quantity_required=quantity, unit=unit)
                db.session.add(new_component)
                db.session.commit()
                flash("Dodano półprodukt do receptury.", "success")
        
        return redirect(url_for('production.manage_recipe', id=id))

    raw_materials = RawMaterial.query.order_by(RawMaterial.name).all()
    sub_products = FinishedProduct.query.filter(FinishedProduct.id != id).order_by(FinishedProduct.name).all()
    return render_template('manage_recipe.html', product=product, raw_materials=raw_materials, sub_products=sub_products)


@bp.route('/recipe/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def edit_recipe_component(id):
    component = RecipeComponent.query.get_or_404(id)
    component.quantity_required = request.form.get('quantity', type=float)
    component.unit = request.form.get('unit')
    db.session.commit()
    flash("Zaktualizowano składnik w recepturze.", "success")
    return redirect(url_for('production.manage_recipe', id=component.finished_product_id))


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
        if not product.recipe_components.first():
            flash(f"Produkt '{product.name}' nie ma zdefiniowanej receptury. Produkcja niemożliwa.", "danger")
            return redirect(url_for('production.manage_production_orders'))
        
        raw_material_plan = []
        sub_product_plan = []
        can_produce = True
        
        for component in product.recipe_components:
            required_quantity = component.quantity_required * batch_size
            if component.raw_material_id:
                available_batches = RawMaterialBatch.query.filter_by(raw_material_id=component.raw_material_id)\
                                                          .filter(RawMaterialBatch.quantity_on_hand > 0)\
                                                          .order_by(RawMaterialBatch.received_date).all()
                total_available = sum(b.quantity_on_hand for b in available_batches)
                if total_available < required_quantity:
                    flash(f"Niewystarczająca ilość surowca: {component.raw_material.name}. Brakuje {required_quantity - total_available:.2f}.", "danger")
                    can_produce = False
                    break
                
                temp_required = required_quantity
                for batch in available_batches:
                    if temp_required <= 0: break
                    quantity_to_take = min(temp_required, batch.quantity_on_hand)
                    raw_material_plan.append({'batch': batch, 'quantity': quantity_to_take})
                    temp_required -= quantity_to_take
            elif component.sub_product_id:
                sub_product = FinishedProduct.query.get(component.sub_product_id)
                if sub_product.quantity_in_stock < required_quantity:
                    flash(f"Niewystarczająca ilość półproduktu: {sub_product.name}. Brakuje {required_quantity - sub_product.quantity_in_stock} szt.", "danger")
                    can_produce = False
                    break
                sub_product_plan.append({'product': sub_product, 'quantity': required_quantity})

        if not can_produce:
            return redirect(url_for('production.manage_production_orders'))
        
        total_weight = sum(c.quantity_required for c in product.recipe_components) * batch_size
        planned_quantity = math.floor(total_weight / product.packaging_weight_kg) if product.packaging_weight_kg > 0 else 0

        if planned_quantity <= 0:
            flash("Wyprodukowana ilość jest zbyt mała, aby stworzyć chociaż jedno opakowanie produktu.", "warning")
            return redirect(url_for('production.manage_production_orders'))

        try:
            new_order = ProductionOrder(finished_product_id=product.id, planned_quantity=planned_quantity, quantity_produced=0)
            db.session.add(new_order)
            db.session.flush()

            for item in raw_material_plan:
                item['batch'].quantity_on_hand -= item['quantity']
                log_entry = ProductionLog(production_order_id=new_order.id, raw_material_batch_id=item['batch'].id, quantity_consumed=item['quantity'])
                db.session.add(log_entry)
            
            for item in sub_product_plan:
                item['product'].quantity_in_stock -= item['quantity']
                
            db.session.commit()
            flash(f"Zlecenie na {planned_quantity} opakowań '{product.name}' zostało utworzone.", "success")
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

                if product.packaging_bill:
                    for item in product.packaging_bill:
                        if item.packaging:
                            item.packaging.quantity_in_stock -= (item.quantity_required * quantity_difference)

            order.quantity_produced = new_produced_quantity
            
            db.session.commit()
            flash(f"Zaktualizowano rzeczywistą ilość w partii. Stany magazynowe produktów i opakowań zostały skorygowane.", "success")
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
        # TODO: Logika zwrotu materiałów musi zostać rozbudowana o półprodukty
        for log in order.consumption_log:
            if log.raw_material_batch_id:
                batch = RawMaterialBatch.query.get(log.raw_material_batch_id)
                if batch:
                    batch.quantity_on_hand += log.quantity_consumed
        
        product = order.finished_product
        product.quantity_in_stock -= order.quantity_produced
        
        if product.packaging_bill:
            for item in product.packaging_bill:
                if item.packaging:
                    item.packaging.quantity_in_stock += (item.quantity_required * order.quantity_produced)
        
        ProductionLog.query.filter_by(production_order_id=order_id).delete()
        db.session.delete(order)
        db.session.commit()
        
        flash("Usunięto wpis z historii produkcji. Wszystkie zużyte materiały zostały zwrócone na stan.", "success")
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


@bp.route('/products/<int:product_id>/packaging', methods=['GET', 'POST'])
@login_required
@permission_required('production')
def manage_packaging_bill(product_id):
    product = FinishedProduct.query.get_or_404(product_id)
    if request.method == 'POST':
        packaging_id = request.form.get('packaging_id', type=int)
        quantity = request.form.get('quantity', type=int)

        if packaging_id and quantity and quantity > 0:
            existing = ProductPackaging.query.filter_by(finished_product_id=product_id, packaging_id=packaging_id).first()
            if existing:
                flash("To opakowanie już jest w specyfikacji. Możesz edytować jego ilość.", "warning")
            else:
                new_component = ProductPackaging(finished_product_id=product_id, packaging_id=packaging_id, quantity_required=quantity)
                db.session.add(new_component)
                db.session.commit()
                flash("Dodano opakowanie do specyfikacji produktu.", "success")
        else:
            flash("Wybierz opakowanie i podaj prawidłową ilość.", "danger")
        return redirect(url_for('production.manage_packaging_bill', product_id=product_id))

    all_packaging = Packaging.query.order_by(Packaging.name).all()
    return render_template('manage_packaging_bill.html', product=product, all_packaging=all_packaging)

@bp.route('/packaging_bill/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def edit_packaging_component(id):
    component = ProductPackaging.query.get_or_404(id)
    component.quantity_required = request.form.get('quantity', type=int)
    db.session.commit()
    flash("Zaktualizowano ilość opakowania.", "success")
    return redirect(url_for('production.manage_packaging_bill', product_id=component.finished_product_id))

@bp.route('/packaging_bill/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def delete_packaging_component(id):
    component = ProductPackaging.query.get_or_404(id)
    product_id = component.finished_product_id
    db.session.delete(component)
    db.session.commit()
    flash("Usunięto opakowanie ze specyfikacji.", "danger")
    return redirect(url_for('production.manage_packaging_bill', product_id=product_id))
    
@bp.route('/recipe/delete_component/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def delete_recipe_component(id):
    # Znajdź składnik, który chcemy usunąć
    component_to_delete = RecipeComponent.query.get_or_404(id)
    
    # Zapisz ID produktu, aby wiedzieć, dokąd wrócić
    product_id = component_to_delete.finished_product_id
    
    # Usuń składnik z bazy danych
    db.session.delete(component_to_delete)
    db.session.commit()
    
    flash('Składnik został usunięty z receptury.', 'success')
    
    # Wróć na stronę edycji receptury tego samego produktu
    return redirect(url_for('production.manage_recipe', id=product_id))