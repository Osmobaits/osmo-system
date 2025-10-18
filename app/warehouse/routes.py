# app/warehouse/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, RawMaterial, Category, RawMaterialBatch, ProductionLog, RecipeComponent
from flask_login import login_required
from app.decorators import permission_required
from datetime import date, datetime
from sqlalchemy.orm import joinedload
from sqlalchemy import asc, desc
from app.utils import log_activity

bp = Blueprint('warehouse', __name__, template_folder='templates', url_prefix='/warehouse')

@bp.route('/', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def index():
    if request.method == 'POST':
        raw_material_id = request.form.get('raw_material_id')
        batch_number = request.form.get('batch_number')
        quantity = request.form.get('quantity')
        unit = request.form.get('unit')
        
        if raw_material_id and batch_number and quantity and unit:
            new_batch = RawMaterialBatch(
                raw_material_id=int(raw_material_id),
                batch_number=batch_number,
                quantity_on_hand=float(quantity),
                unit=unit,
                received_date=date.today()
            )
            db.session.add(new_batch)
            db.session.commit()

            # Logowanie aktywności
            log_activity(f"Przyjął na stan partię surowca '{new_batch.material.name}' "
                         f"(nr: {new_batch.batch_number}, ilość: {new_batch.quantity_on_hand} {new_batch.unit})",
                         'warehouse.edit_batch', id=new_batch.id)

            flash(f"Dodano nową partię surowca.", "success")
        else:
            flash("Wszystkie pola są wymagane.", "warning")
        return redirect(url_for('warehouse.index'))

    sort_by = request.args.get('sort_by', 'received_date')
    order = request.args.get('order', 'desc')
    query = RawMaterialBatch.query.join(RawMaterial).filter(RawMaterialBatch.quantity_on_hand > 0)
    sort_map = {
        'received_date': RawMaterialBatch.received_date,
        'name': RawMaterial.name,
        'batch_number': RawMaterialBatch.batch_number,
        'quantity': RawMaterialBatch.quantity_on_hand,
    }
    sort_column = sort_map.get(sort_by, RawMaterialBatch.received_date)
    
    if order == 'asc':
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))
        
    all_batches = query.all()
    categories = Category.query.options(joinedload(Category.raw_materials)).order_by(Category.name).all()

    total_stocks = {}
    for batch in RawMaterialBatch.query.all():
        total_stocks[batch.raw_material_id] = total_stocks.get(batch.raw_material_id, 0) + batch.quantity_on_hand

    low_stock_materials = []
    all_materials = RawMaterial.query.all()
    for material in all_materials:
        current_stock = total_stocks.get(material.id, 0)
        if material.critical_stock_level > 0 and current_stock < material.critical_stock_level:
            material.current_stock = current_stock
            low_stock_materials.append(material)

    return render_template('warehouse_index.html', 
                           categories=categories, 
                           batches=all_batches, 
                           low_stock_materials=low_stock_materials,
                           total_stocks=total_stocks,
                           sort_by=sort_by,
                           order=order)


@bp.route('/batch/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def edit_batch(id):
    batch_to_edit = RawMaterialBatch.query.get_or_404(id)
    if request.method == 'POST':
        batch_to_edit.batch_number = request.form.get('batch_number')
        batch_to_edit.quantity_on_hand = float(request.form.get('quantity_on_hand'))
        batch_to_edit.unit = request.form.get('unit')
        date_str = request.form.get('received_date')
        if date_str:
            batch_to_edit.received_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        db.session.commit()
        flash(f"Zaktualizowano dane partii nr: {batch_to_edit.batch_number}", "success")
        return redirect(url_for('warehouse.index'))
        
    return render_template('edit_raw_material_batch.html', batch=batch_to_edit)

@bp.route('/batch/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('warehouse')
def delete_batch(id):
    batch_to_delete = RawMaterialBatch.query.get_or_404(id)
    
    usage_in_log = ProductionLog.query.filter_by(raw_material_batch_id=id).first()
    
    if usage_in_log:
        flash(f"Nie można usunąć partii '{batch_to_delete.batch_number}', ponieważ została już użyta w produkcji. Możesz edytować jej ilość, np. ustawiając ją na 0.", "danger")
    else:
        db.session.delete(batch_to_delete)
        db.session.commit()
        flash(f"Partia '{batch_to_delete.batch_number}' została usunięta.", "success")
        
    return redirect(url_for('warehouse.index'))


@bp.route('/catalogue', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def manage_catalogue():
    if request.method == 'POST':
        name = request.form.get('name')
        category_id = request.form.get('category_id')
        
        if name and category_id:
            existing_material = RawMaterial.query.filter_by(name=name).first()
            if existing_material:
                flash(f"Surowiec o nazwie '{name}' już istnieje w katalogu. Proszę podać inną nazwę.", "warning")
            else:
                new_material = RawMaterial(name=name, category_id=int(category_id))
                db.session.add(new_material)
                db.session.commit()
                flash(f"Dodano surowiec '{name}' do katalogu.", "success")
        
        return redirect(url_for('warehouse.manage_catalogue'))
    
    categories = Category.query.options(
        joinedload(Category.raw_materials)
    ).order_by(Category.name).all()
    
    return render_template('manage_raw_materials_catalogue.html', categories=categories)


@bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def edit_material(id):
    material_to_edit = RawMaterial.query.get_or_404(id)
    if request.method == 'POST':
        material_to_edit.name = request.form.get('name')
        material_to_edit.category_id = int(request.form.get('category_id'))
        material_to_edit.critical_stock_level = float(request.form.get('critical_stock_level', 0))
        db.session.commit()
        flash(f"Zaktualizowano surowiec: {material_to_edit.name}", "success")
        return redirect(url_for('warehouse.manage_catalogue'))
    all_categories = Category.query.order_by(Category.name).all()
    return render_template('edit_material.html', material=material_to_edit, categories=all_categories)

@bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('warehouse')
def delete_material(id):
    material_to_delete = RawMaterial.query.get_or_404(id)
    
    usage_in_recipe = RecipeComponent.query.filter_by(raw_material_id=id).first()
    
    if usage_in_recipe:
        # === POCZĄTEK ZMIANY: UŻYCIE POPRAWNEJ NAZWY RELACJI ===
        product_name = usage_in_recipe.product.name
        # === KONIEC ZMIANY ===
        flash(f"Nie można usunąć surowca '{material_to_delete.name}', ponieważ jest on używany w recepturze produktu '{product_name}'.", "danger")
    else:
        db.session.delete(material_to_delete)
        db.session.commit()
        flash(f"Usunięto surowiec: {material_to_delete.name}", "success")
        
    return redirect(url_for('warehouse.manage_catalogue'))


@bp.route('/categories', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def manage_categories():
    if request.method == 'POST':
        category_name = request.form.get('name')
        if category_name:
            existing_category = Category.query.filter_by(name=category_name).first()
            if not existing_category:
                new_category = Category(name=category_name)
                db.session.add(new_category)
                db.session.commit()
                flash(f"Dodano kategorię: {category_name}", "success")
            else:
                flash("Kategoria o tej nazwie już istnieje.", "warning")
        return redirect(url_for('warehouse.manage_categories'))
    all_categories = Category.query.order_by(Category.name).all()
    return render_template('manage_categories.html', categories=all_categories)

@bp.route('/categories/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('warehouse')
def edit_category(id):
    category = Category.query.get_or_404(id)
    new_name = request.form.get('name')
    if new_name:
        category.name = new_name
        db.session.commit()
        flash("Nazwa kategorii została zaktualizowana.", "success")
    return redirect(url_for('warehouse.manage_categories'))

@bp.route('/categories/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('warehouse')
def delete_category(id):
    category = Category.query.get_or_404(id)
    if category.raw_materials:
        flash(f"Nie można usunąć kategorii '{category.name}', ponieważ są do niej przypisane surowce.", "danger")
    else:
        db.session.delete(category)
        db.session.commit()
        flash(f"Kategoria '{category.name}' została usunięta.", "danger")
    return redirect(url_for('warehouse.manage_categories'))