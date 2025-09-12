# app/warehouse/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, RawMaterial, Category, RawMaterialBatch
from flask_login import login_required
from app.decorators import permission_required
from datetime import date
from sqlalchemy.orm import joinedload

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
            flash(f"Dodano nową partię surowca.", "success")
        else:
            flash("Wszystkie pola są wymagane.", "warning")
        return redirect(url_for('warehouse.index'))

    categories = Category.query.options(joinedload(Category.raw_materials)).order_by(Category.name).all()
    all_batches = RawMaterialBatch.query.order_by(RawMaterialBatch.received_date.desc()).all()
    return render_template('warehouse_index.html', categories=categories, batches=all_batches)

@bp.route('/catalogue', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def manage_catalogue():
    if request.method == 'POST':
        name = request.form.get('name')
        category_id = request.form.get('category_id')

        # === POCZĄTEK ZMIANY: SPRAWDZENIE CZY NAZWA ISTNIEJE ===
        if name and category_id:
            existing_material = RawMaterial.query.filter_by(name=name).first()
            if existing_material:
                flash(f"Surowiec o nazwie '{name}' już istnieje w katalogu. Proszę podać inną nazwę.", "warning")
            else:
                new_material = RawMaterial(name=name, category_id=int(category_id))
                db.session.add(new_material)
                db.session.commit()
                flash(f"Dodano surowiec '{name}' do katalogu.", "success")
        # === KONIEC ZMIANY ===
        
        return redirect(url_for('warehouse.manage_catalogue'))
    
    materials = RawMaterial.query.order_by(RawMaterial.name).all()
    categories = Category.query.order_by(Category.name).all()
    return render_template('manage_raw_materials_catalogue.html', materials=materials, categories=categories)

@bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def edit_material(id):
    material_to_edit = RawMaterial.query.get_or_404(id)
    if request.method == 'POST':
        material_to_edit.name = request.form.get('name')
        material_to_edit.category_id = int(request.form.get('category_id'))
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
    db.session.delete(material_to_delete)
    db.session.commit()
    flash(f"Usunięto surowiec: {material_to_delete.name}", "danger")
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
    db.session.delete(category)
    db.session.commit()
    flash(f"Kategoria '{category.name}' oraz powiązane z nią surowce zostały usunięte.", "danger")
    return redirect(url_for('warehouse.manage_categories'))