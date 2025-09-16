# app/packaging/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, Packaging, PackagingCategory
from flask_login import login_required
from app.decorators import permission_required
from sqlalchemy.orm import joinedload

bp = Blueprint('packaging', __name__, template_folder='templates', url_prefix='/packaging')

@bp.route('/', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def index():
    if request.method == 'POST':
        name = request.form.get('name')
        quantity = request.form.get('quantity', type=int)
        category_id = request.form.get('category_id', type=int)

        if name and quantity is not None and quantity >= 0 and category_id:
            existing_packaging = Packaging.query.filter_by(name=name).first()
            if existing_packaging:
                flash(f"Opakowanie o nazwie '{name}' już istnieje.", "warning")
            else:
                new_packaging = Packaging(name=name, quantity_in_stock=quantity, category_id=category_id)
                db.session.add(new_packaging)
                db.session.commit()
                flash(f"Dodano nowe opakowanie '{name}' na stan.", "success")
        else:
            flash("Nazwa, kategoria i ilość są wymagane.", "danger")
        return redirect(url_for('packaging.index'))

    # === POCZĄTEK ZMIANY ===
    # Pobieramy kategorie z przypisanymi opakowaniami
    categories = PackagingCategory.query.options(joinedload(PackagingCategory.packaging_items)).order_by(PackagingCategory.name).all()
    # Pobieramy osobną listę opakowań bez kategorii
    uncategorized_packaging = Packaging.query.filter(Packaging.category_id == None).order_by(Packaging.name).all()
    
    return render_template('packaging_index.html', categories=categories, uncategorized_packaging=uncategorized_packaging)
    # === KONIEC ZMIANY ===

@bp.route('/edit_stock/<int:packaging_id>', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def edit_stock(packaging_id):
    packaging_item = Packaging.query.get_or_404(packaging_id)
    if request.method == 'POST':
        new_quantity = request.form.get('quantity_in_stock', type=int)
        if new_quantity is not None and new_quantity >= 0:
            packaging_item.quantity_in_stock = new_quantity
            db.session.commit()
            flash(f"Zaktualizowano stan magazynowy dla '{packaging_item.name}'.", "success")
            return redirect(url_for('packaging.index'))
        else:
            flash("Podano nieprawidłową wartość.", "danger")
    
    return render_template('edit_packaging_stock.html', packaging_item=packaging_item)

@bp.route('/delete/<int:packaging_id>', methods=['POST'])
@login_required
@permission_required('warehouse')
def delete_packaging(packaging_id):
    packaging_item = Packaging.query.get_or_404(packaging_id)
    if packaging_item.products:
        flash(f"Nie można usunąć opakowania '{packaging_item.name}', ponieważ jest ono przypisane do produktów w katalogu.", "danger")
    else:
        db.session.delete(packaging_item)
        db.session.commit()
        flash(f"Opakowanie '{packaging_item.name}' zostało usunięte.", "success")
    return redirect(url_for('packaging.index'))


@bp.route('/categories', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def manage_categories():
    if request.method == 'POST':
        category_name = request.form.get('name')
        if category_name:
            existing_category = PackagingCategory.query.filter_by(name=category_name).first()
            if not existing_category:
                new_category = PackagingCategory(name=category_name)
                db.session.add(new_category)
                db.session.commit()
                flash(f"Dodano kategorię: {category_name}", "success")
            else:
                flash("Kategoria o tej nazwie już istnieje.", "warning")
        return redirect(url_for('packaging.manage_categories'))
    
    all_categories = PackagingCategory.query.order_by(PackagingCategory.name).all()
    return render_template('manage_pkg_categories.html', categories=all_categories)

@bp.route('/categories/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('admin')
def edit_category(id):
    category = PackagingCategory.query.get_or_404(id)
    new_name = request.form.get('name')
    if new_name:
        category.name = new_name
        db.session.commit()
        flash("Nazwa kategorii została zaktualizowana.", "success")
    return redirect(url_for('packaging.manage_categories'))

@bp.route('/categories/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('admin')
def delete_category(id):
    category = PackagingCategory.query.get_or_404(id)
    if category.packaging_items:
        flash(f"Nie można usunąć kategorii '{category.name}', ponieważ są do niej przypisane opakowania.", "danger")
    else:
        db.session.delete(category)
        db.session.commit()
        flash(f"Kategoria '{category.name}' została usunięta.", "danger")
    return redirect(url_for('packaging.manage_categories'))