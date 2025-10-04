# app/packaging/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, Packaging, PackagingCategory
from flask_login import login_required
from app.decorators import permission_required
from sqlalchemy.orm import joinedload
from sqlalchemy import asc, desc

bp = Blueprint('packaging', __name__, template_folder='templates', url_prefix='/packaging')

@bp.route('/', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def index():
    if request.method == 'POST':
        # Logika dodawania nowego opakowania (bez zmian)
        name = request.form.get('name')
        category_id = request.form.get('category_id')
        quantity = request.form.get('quantity')
        critical_stock_level = request.form.get('critical_stock_level')
        
        new_packaging = Packaging(
            name=name,
            category_id=int(category_id),
            quantity_in_stock=int(quantity),
            critical_stock_level=int(critical_stock_level)
        )
        db.session.add(new_packaging)
        db.session.commit()
        flash('Dodano nowe opakowanie na stan.', 'success')
        return redirect(url_for('packaging.index'))

    # Logika wyświetlania i sortowania
    sort_by = request.args.get('sort_by', 'name')
    order = request.args.get('order', 'asc')

    sort_map = {
        'name': Packaging.name,
        'quantity': Packaging.quantity_in_stock,
    }
    sort_column = sort_map.get(sort_by, Packaging.name)

    if order == 'asc':
        query = Packaging.query.order_by(asc(sort_column))
    else:
        query = Packaging.query.order_by(desc(sort_column))
    
    all_packaging = query.all()

    # --- NOWY FRAGMENT ---
    # Wyszukaj opakowania poniżej stanu krytycznego
    low_stock_packaging = [
        p for p in all_packaging 
        if p.critical_stock_level > 0 and p.quantity_in_stock < p.critical_stock_level
    ]
    # ---------------------

    categories = PackagingCategory.query.order_by(PackagingCategory.name).all()
    
    return render_template('packaging_index.html', 
                           categories=categories, 
                           all_packaging=all_packaging,
                           low_stock_packaging=low_stock_packaging, # <-- Przekazanie do widoku
                           sort_by=sort_by,
                           order=order)

@bp.route('/edit_stock/<int:packaging_id>', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def edit_stock(packaging_id):
    packaging_item = Packaging.query.get_or_404(packaging_id)
    if request.method == 'POST':
        new_quantity = request.form.get('quantity_in_stock', type=int)
        critical_stock_level = request.form.get('critical_stock_level', type=int) # <-- NOWA LINIA
        
        if new_quantity is not None and new_quantity >= 0 and critical_stock_level is not None: # <-- ZMIANA
            packaging_item.quantity_in_stock = new_quantity
            packaging_item.critical_stock_level = critical_stock_level # <-- NOWA LINIA
            db.session.commit()
            flash(f"Zaktualizowano dane dla '{packaging_item.name}'.", "success")
            return redirect(url_for('packaging.index'))
        else:
            flash("Podano nieprawidłowe wartości.", "danger")
    
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