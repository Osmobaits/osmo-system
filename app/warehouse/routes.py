# app/warehouse/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, RawMaterial, Category
from flask_login import login_required
from app.decorators import permission_required

bp = Blueprint('warehouse', __name__, template_folder='templates', url_prefix='/warehouse')

@bp.route('/', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def index():
    if request.method == 'POST':
        name = request.form.get('name')
        quantity = request.form.get('quantity')
        unit = request.form.get('unit')
        category_id = request.form.get('category_id')
        if name and quantity and unit and category_id:
            existing_material = RawMaterial.query.filter_by(name=name).first()
            if existing_material:
                flash(f'Surowiec o nazwie "{name}" już istnieje w magazynie.', 'warning')
            else:
                new_material = RawMaterial(name=name, quantity_in_stock=float(quantity), unit=unit, category_id=int(category_id))
                db.session.add(new_material)
                db.session.commit()
                flash(f"Dodano surowiec: {name}", "success")
            return redirect(url_for('warehouse.index'))
            
    all_materials = RawMaterial.query.order_by(RawMaterial.name).all()
    all_categories = Category.query.order_by(Category.name).all()
    return render_template('warehouse_index.html', materials=all_materials, categories=all_categories)

@bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def edit_material(id):
    material_to_edit = RawMaterial.query.get_or_404(id)
    if request.method == 'POST':
        material_to_edit.name = request.form.get('name')
        material_to_edit.quantity_in_stock = float(request.form.get('quantity'))
        material_to_edit.unit = request.form.get('unit')
        material_to_edit.category_id = int(request.form.get('category_id'))
        db.session.commit()
        flash(f"Zaktualizowano surowiec: {material_to_edit.name}", "success")
        return redirect(url_for('warehouse.index'))
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
    return redirect(url_for('warehouse.index'))

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