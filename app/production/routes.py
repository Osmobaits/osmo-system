# app/production/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models import db, FinishedProduct, RawMaterial, RecipeComponent, ProductionOrder, RawMaterialBatch, ProductionLog, FinishedProductCategory, Packaging, ProductPackaging
from flask_login import login_required
from app.decorators import permission_required
import math
from app.utils import log_activity

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
            flash('Proszę wybrać produkt i podać prawidłową liczbę porcji.', 'warning')
            return redirect(url_for('production.manage_production_orders'))

        product = FinishedProduct.query.get_or_404(product_id)
        
        missing_components = []
        missing_packaging = []

        # === KROK 1: WERYFIKACJA SUROWCÓW I PÓŁPRODUKTÓW ===
        total_recipe_weight_kg = 0.0
        for component in product.recipe_components:
            # Obliczanie wagi receptury z uwzględnieniem jednostek
            quantity_kg = component.quantity_required
            if component.unit == 'g':
                quantity_kg /= 1000
            elif component.unit == 'ml':
                quantity_kg /= 1000 # Założenie, że 1ml ~ 1g
            
            if component.unit in ['kg', 'g', 'ml']:
                 total_recipe_weight_kg += quantity_kg
            
            required_quantity = component.quantity_required * batch_size
            
            if component.raw_material:
                total_stock = sum(batch.quantity_on_hand for batch in component.raw_material.batches)
                if total_stock < required_quantity:
                    missing_components.append(f"{component.raw_material.name} (brakuje: {required_quantity - total_stock:.2f} {component.unit})")
            
            elif component.sub_product:
                if component.sub_product.quantity_in_stock < required_quantity:
                    missing_components.append(f"{component.sub_product.name} (brakuje: {required_quantity - component.sub_product.quantity_in_stock:.2f} {component.unit})")

        # === NOWA, POPRAWNA LOGIKA OBLICZANIA PLANOWANEJ ILOŚCI ===
        planned_quantity = 0
        if product.packaging_weight_kg > 0:
            total_production_weight = total_recipe_weight_kg * batch_size
            planned_quantity = int(total_production_weight / product.packaging_weight_kg)
        else:
            # Jeśli waga opakowania to 0, użyj mnożnika jako ilości sztuk
            planned_quantity = batch_size
        # ==========================================================

        # === KROK 2: WERYFIKACJA OPAKOWAŃ ===
        for item in product.packaging_bill:
            required_packaging = item.quantity_required * planned_quantity
            if item.packaging.quantity_in_stock < required_packaging:
                missing_packaging.append(f"{item.packaging.name} (brakuje: {required_packaging - item.packaging.quantity_in_stock})")

        # === KROK 3: OBSŁUGA BRAKÓW ===
        if missing_components or missing_packaging:
            error_message = "Brak wystarczających zasobów do rozpoczęcia produkcji. Brakuje:<br>"
            if missing_components:
                error_message += "<b>Składniki:</b><ul>" + "".join(f"<li>{m}</li>" for m in missing_components) + "</ul>"
            if missing_packaging:
                error_message += "<b>Opakowania:</b><ul>" + "".join(f"<li>{m}</li>" for m in missing_packaging) + "</ul>"
            flash(Markup(error_message), 'danger')
            return redirect(url_for('production.manage_production_orders'))

        # === KROK 4: WYSTARCZAJĄCE ZASOBY - ROZPOCZNIJ PRODUKCJĘ ===
        new_order = ProductionOrder(
            finished_product_id=product.id,
            planned_quantity=planned_quantity, # <-- Użycie nowej, poprawnej wartości
            quantity_produced=0,
            sample_required=False 
        )
        db.session.add(new_order)
        db.session.flush()

        # Odejmowanie zasobów z magazynu
        for component in product.recipe_components:
            required_quantity = component.quantity_required * batch_size
            
            if component.raw_material:
                batches = sorted(component.raw_material.batches, key=lambda b: b.received_date)
                for batch in batches:
                    if required_quantity <= 0: break
                    take_qty = min(batch.quantity_on_hand, required_quantity)
                    batch.quantity_on_hand -= take_qty
                    
                    log = ProductionLog(production_order_id=new_order.id, raw_material_batch_id=batch.id, quantity_consumed=take_qty)
                    db.session.add(log)
                    
                    required_quantity -= take_qty
            
            elif component.sub_product:
                component.sub_product.quantity_in_stock -= required_quantity

        db.session.commit()

        # Logowanie aktywności
        log_activity(f"Utworzył zlecenie produkcyjne #{new_order.id} dla produktu: '{product.name}'",
                     'production.production_order_details', order_id=new_order.id)

        flash('Utworzono nowe zlecenie produkcyjne i pobrano zasoby z magazynu.', 'success')
        return redirect(url_for('production.manage_production_orders'))

    # Kod dla metody GET (wyświetlanie strony)
    products = FinishedProduct.query.order_by(FinishedProduct.name).all()
    orders = ProductionOrder.query.order_by(ProductionOrder.order_date.desc()).all()
    return render_template('production_orders.html', products=products, orders=orders)


@bp.route('/batch/edit/<int:order_id>', methods=['GET', 'POST'])
@login_required
@permission_required('production')
def edit_batch(order_id):
    batch = ProductionOrder.query.get_or_404(order_id)
    product = batch.finished_product
    original_quantity_produced = batch.quantity_produced

    if request.method == 'POST':
        new_quantity_produced = request.form.get('quantity', type=int)
        quantity_diff = new_quantity_produced - original_quantity_produced

        batch.quantity_produced = new_quantity_produced
        product.quantity_in_stock += quantity_diff

        if quantity_diff != 0:
            for item in product.packaging_bill:
                packaging_item = item.packaging
                packaging_item.quantity_in_stock -= (item.quantity_required * quantity_diff)

        db.session.commit()

        # Logowanie aktywności
        log_activity(f"Zakończył produkcję partii #{batch.id} ('{batch.finished_product.name}'), "
                     f"produkując {batch.quantity_produced} szt.",
                     'production.production_order_details', order_id=batch.id)

        flash(f"Zaktualizowano partię produkcyjną. Stan magazynowy produktu '{product.name}' został zaktualizowany.", "success")
        return redirect(url_for('production.manage_products'))

    return render_template('edit_batch.html', batch=batch)


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