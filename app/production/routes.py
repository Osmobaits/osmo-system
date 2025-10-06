# app/production/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models import db, FinishedProduct, RawMaterial, RecipeComponent, ProductionOrder, RawMaterialBatch, ProductionLog, FinishedProductCategory, Packaging, ProductPackaging
from markupsafe import Markup
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
        # --- LOGIKA ZAPISU ---
        name = request.form.get('name')
        product_code = request.form.get('product_code')
        category_id = request.form.get('category_id')
        
        packaging_weight_str = request.form.get('packaging_weight')
        packaging_weight = float(packaging_weight_str) if packaging_weight_str else 0.0
        
        unit = request.form.get('unit')

        # Przelicz na KG do zapisu w bazie, jeśli jednostka to g lub ml
        weight_in_kg = packaging_weight
        if unit.lower() in ['g', 'ml']:
            weight_in_kg = packaging_weight / 1000.0

        new_product = FinishedProduct(
            name=name,
            product_code=product_code,
            category_id=int(category_id),
            packaging_weight_kg=weight_in_kg, # Zawsze zapisuj wagę w KG
            unit=unit  # Zapisz oryginalną jednostkę wybraną przez użytkownika
        )
        db.session.add(new_product)
        db.session.commit()
        flash('Dodano nowy produkt do katalogu.', 'success')
        return redirect(url_for('production.manage_catalogue'))

    # --- LOGIKA WYŚWIETLANIA ---
    categories = FinishedProductCategory.query.order_by(FinishedProductCategory.name).all()
    
    # Przygotuj dane do wyświetlenia w formularzu
    for category in categories:
        for product in category.finished_products:
            # Domyślnie użyj wagi w kg
            product.display_weight = product.packaging_weight_kg
            # Jeśli zapisaną jednostką są gramy/ml, przelicz z powrotem do wyświetlenia
            if product.unit and product.unit.lower() in ['g', 'ml']:
                product.display_weight = round(product.packaging_weight_kg * 1000, 2)
    
    return render_template('manage_catalogue.html', categories=categories)

@bp.route('/catalogue/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('production')
def edit_catalogue_product(id):
    product = FinishedProduct.query.get_or_404(id)
    product.name = request.form.get('name')
    product.product_code = request.form.get('product_code')
    product.category_id = int(request.form.get('category_id'))
    
    packaging_weight_str = request.form.get('packaging_weight')
    packaging_weight = float(packaging_weight_str) if packaging_weight_str else 0.0
    
    unit = request.form.get('unit')

    # Przelicz na KG do zapisu w bazie, jeśli jednostka to g lub ml
    weight_in_kg = packaging_weight
    if unit.lower() in ['g', 'ml']:
        weight_in_kg = packaging_weight / 1000.0
    
    product.packaging_weight_kg = weight_in_kg # Zawsze zapisuj wagę w KG
    product.unit = unit  # Zapisz oryginalną jednostkę wybraną przez użytkownika
    
    db.session.commit()
    flash(f"Zaktualizowano produkt '{product.name}'.", 'success')
    return redirect(url_for('production.manage_catalogue'))

@bp.route('/catalogue/check_code')
@login_required
@permission_required('production')
def check_product_code():
    code = request.args.get('code', '', type=str)
    if not code:
        return jsonify({'exists': False})
    
    product = FinishedProduct.query.filter_by(product_code=code).first()
    return jsonify({'exists': product is not None})


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

        # --- POCZĄTEK KODU DIAGNOSTYCZNEGO ---
        print("\n--- [DEBUG] Rozpoczynanie nowego zlecenia ---")
        # --- KONIEC KODU DIAGNOSTYCZNEGO ---

        if not product_id or not batch_size or batch_size <= 0:
            flash('Proszę wybrać produkt i podać prawidłową liczbę porcji.', 'warning')
            return redirect(url_for('production.manage_production_orders'))

        product = FinishedProduct.query.get_or_404(product_id)
        
        if not product.recipe_components.first():
            flash(f"BŁĄD: Nie można utworzyć zlecenia. Produkt '{product.name}' nie ma zdefiniowanej receptury.", 'danger')
            return redirect(url_for('production.manage_production_orders'))

        missing_components = []
        missing_packaging = []

        def convert_unit(quantity, from_unit, to_unit='g'): # Uproszczone, bo w tej funkcji zawsze przeliczamy na gramy
            from_unit = from_unit.lower()
            if from_unit == 'kg':
                return quantity * 1000
            elif from_unit in ['g', 'ml']:
                return quantity
            return 0

        total_recipe_weight_g = 0
        print("--- [DEBUG] Obliczanie wagi receptury:")
        for component in product.recipe_components:
            component_weight_g = convert_unit(component.quantity_required, component.unit)
            component_name = "Nieznany"
            if component.raw_material:
                component_name = component.raw_material.name
            elif component.sub_product:
                component_name = component.sub_product.name
            print(f"    - Składnik: '{component_name}' | Ilość: {component.quantity_required} {component.unit} -> Przeliczono na: {component_weight_g}g")
            total_recipe_weight_g += component_weight_g
        
        print(f"--- [DEBUG] Całkowita waga receptury: {total_recipe_weight_g}g")
        
        planned_quantity = 0
        packaging_weight_g = product.packaging_weight_kg * 1000
        
        print(f"--- [DEBUG] Waga opakowania: {packaging_weight_g}g | Mnożnik (batch_size): {batch_size}")

        if packaging_weight_g > 0:
            total_production_weight_g = total_recipe_weight_g * batch_size
            print(f"--- [DEBUG] Całkowita waga produkcji: {total_production_weight_g}g")
            planned_quantity = int(total_production_weight_g / packaging_weight_g)
        else:
            planned_quantity = batch_size
            
        print(f"--- [DEBUG] Finalna planowana ilość: {planned_quantity} szt.")
        print("-------------------------------------------\n")
        
        # Reszta funkcji bez zmian...
        for component in product.recipe_components:
            required_quantity_orig_unit = component.quantity_required * batch_size
            if component.raw_material:
                total_stock_in_component_unit = 0
                for batch in component.raw_material.batches:
                    total_stock_in_component_unit += convert_unit(batch.quantity_on_hand, batch.unit, component.unit)
                if total_stock_in_component_unit < required_quantity_orig_unit:
                    shortage = required_quantity_orig_unit - total_stock_in_component_unit
                    missing_components.append(f"{component.raw_material.name} (brakuje: {shortage:.0f} {component.unit})")
            elif component.sub_product:
                if component.sub_product.quantity_in_stock < required_quantity_orig_unit:
                    missing_components.append(f"{component.sub_product.name} (brakuje: {int(required_quantity_orig_unit - component.sub_product.quantity_in_stock)} szt.)")

        for item in product.packaging_bill:
            required_packaging = item.quantity_required * planned_quantity
            if item.packaging.quantity_in_stock < required_packaging:
                missing_packaging.append(f"{item.packaging.name} (brakuje: {required_packaging - item.packaging.quantity_in_stock})")

        if missing_components or missing_packaging:
            error_message = "Brak wystarczających zasobów do rozpoczęcia produkcji. Brakuje:<br>"
            if missing_components:
                error_message += "<b>Składniki:</b><ul>" + "".join(f"<li>{m}</li>" for m in missing_components) + "</ul>"
            if missing_packaging:
                error_message += "<b>Opakowania:</b><ul>" + "".join(f"<li>{m}</li>" for m in missing_packaging) + "</ul>"
            flash(Markup(error_message), 'danger')
            return redirect(url_for('production.manage_production_orders'))

        new_order = ProductionOrder(finished_product_id=product.id, planned_quantity=planned_quantity, quantity_produced=0, sample_required=False)
        db.session.add(new_order)
        db.session.flush()

        for component in product.recipe_components:
            if component.raw_material:
                required_g = convert_unit(component.quantity_required * batch_size, component.unit)
                batches = sorted(component.raw_material.batches, key=lambda b: b.received_date)
                for batch in batches:
                    if required_g <= 0: break
                    batch_g = convert_unit(batch.quantity_on_hand, batch.unit)
                    take_g = min(batch_g, required_g)
                    remaining_g = batch_g - take_g
                    batch.quantity_on_hand = convert_unit(remaining_g, 'g', batch.unit)
                    consumed_orig_unit = convert_unit(take_g, 'g', batch.unit)
                    log = ProductionLog(production_order_id=new_order.id, raw_material_batch_id=batch.id, quantity_consumed=consumed_orig_unit)
                    db.session.add(log)
                    required_g -= take_g
            elif component.sub_product:
                component.sub_product.quantity_in_stock -= (component.quantity_required * batch_size)

        db.session.commit()
        log_activity(f"Utworzył zlecenie produkcyjne #{new_order.id} dla produktu: '{product.name}'", 'production.production_order_details', order_id=new_order.id)
        flash('Utworzono nowe zlecenie produkcyjne i pobrano zasoby z magazynu.', 'success')
        return redirect(url_for('production.manage_production_orders'))

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