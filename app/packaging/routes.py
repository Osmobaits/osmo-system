# app/packaging/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, Packaging
from flask_login import login_required
from app.decorators import permission_required

bp = Blueprint('packaging', __name__, template_folder='templates', url_prefix='/packaging')

@bp.route('/', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def index():
    if request.method == 'POST':
        name = request.form.get('name')
        quantity = request.form.get('quantity', type=int)

        if name and quantity is not None and quantity >= 0:
            existing_packaging = Packaging.query.filter_by(name=name).first()
            if existing_packaging:
                flash(f"Opakowanie o nazwie '{name}' już istnieje.", "warning")
            else:
                new_packaging = Packaging(name=name, quantity_in_stock=quantity)
                db.session.add(new_packaging)
                db.session.commit()
                flash(f"Dodano nowe opakowanie '{name}' na stan.", "success")
        else:
            flash("Nazwa i ilość są wymagane.", "danger")
        return redirect(url_for('packaging.index'))

    all_packaging = Packaging.query.order_by(Packaging.name).all()
    return render_template('packaging_index.html', all_packaging=all_packaging)

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