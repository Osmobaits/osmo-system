from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, FinishedProduct, FinishedProductCategory
from flask_login import login_required
from app.decorators import permission_required
from sqlalchemy import asc, desc

bp = Blueprint('finished_goods', __name__, template_folder='templates', url_prefix='/finished_goods')

@bp.route('/')
@login_required
@permission_required('warehouse')
def index():
    categories = FinishedProductCategory.query.order_by(FinishedProductCategory.name).all()
    
    sort_by = request.args.get('sort_by', 'name')
    order = request.args.get('order', 'asc')

    sort_map = {
        'name': FinishedProduct.name,
        'quantity': FinishedProduct.quantity_in_stock,
    }
    sort_column = sort_map.get(sort_by, FinishedProduct.name)

    if order == 'asc':
        query = FinishedProduct.query.order_by(asc(sort_column))
    else:
        query = FinishedProduct.query.order_by(desc(sort_column))
    
    all_products = query.all()

    low_stock_products = [p for p in all_products if p.critical_stock_level > 0 and p.quantity_in_stock < p.critical_stock_level]
    
    return render_template('finished_goods_index.html', 
                           categories=categories, 
                           all_products=all_products,
                           low_stock_products=low_stock_products,
                           sort_by=sort_by,
                           order=order)

@bp.route('/edit_stock/<int:product_id>', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def edit_product_stock(product_id):
    product = FinishedProduct.query.get_or_404(product_id)
    if request.method == 'POST':
        product.quantity_in_stock = request.form.get('quantity_in_stock', type=int)
        product.critical_stock_level = request.form.get('critical_stock_level', type=int)
        db.session.commit()
        flash(f"Zaktualizowano dane dla produktu '{product.name}'.", 'success')
        return redirect(url_for('finished_goods.index'))
    return render_template('edit_fp_stock.html', product=product)

@bp.route('/categories', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def manage_categories():
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            existing_category = FinishedProductCategory.query.filter_by(name=name).first()
            if not existing_category:
                new_category = FinishedProductCategory(name=name)
                db.session.add(new_category)
                db.session.commit()
                flash(f"Dodano nową kategorię: {name}", 'success')
            else:
                flash('Kategoria o tej nazwie już istnieje.', 'warning')
        return redirect(url_for('finished_goods.manage_categories'))
    
    categories = FinishedProductCategory.query.order_by(FinishedProductCategory.name).all()
    return render_template('manage_fp_categories.html', categories=categories)

@bp.route('/categories/edit/<int:id>', methods=['POST'])
@login_required
@permission_required('admin')
def edit_category(id):
    category = FinishedProductCategory.query.get_or_404(id)
    new_name = request.form.get('name')
    if new_name:
        category.name = new_name
        db.session.commit()
        flash("Nazwa kategorii została zaktualizowana.", "success")
    return redirect(url_for('finished_goods.manage_categories'))

@bp.route('/categories/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('admin')
def delete_category(id):
    category = FinishedProductCategory.query.get_or_404(id)
    if category.finished_products:
        flash(f"Nie można usunąć kategorii '{category.name}', ponieważ są do niej przypisane produkty.", 'danger')
    else:
        db.session.delete(category)
        db.session.commit()
        flash(f"Kategoria '{category.name}' została usunięta.", 'success')
    return redirect(url_for('finished_goods.manage_categories'))

@bp.route('/categories/toggle_team_availability/<int:category_id>', methods=['POST'])
@login_required
@permission_required('admin')
def toggle_team_availability(category_id):
    category = FinishedProductCategory.query.get_or_404(category_id)
    category.available_for_team = not category.available_for_team
    db.session.commit()
    
    status = "udostępniona" if category.available_for_team else "ukryta"
    flash(f"Kategoria '{category.name}' została {status} dla drużyny.", "success")
    return redirect(url_for('finished_goods.manage_categories'))

@bp.route('/import_sales', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def import_sales():
    if request.method == 'POST':
        # Tutaj w przyszłości będzie logika przetwarzania pliku PDF
        flash('Funkcjonalność importu sprzedaży nie jest jeszcze zaimplementowana.', 'info')
        return redirect(url_for('finished_goods.index'))
    
    # Na razie tylko wyświetlamy pusty szablon
    return render_template('import_sales.html')