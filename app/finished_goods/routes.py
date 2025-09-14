# app/finished_goods/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, FinishedProductCategory, FinishedProduct
from flask_login import login_required
from app.decorators import permission_required
from sqlalchemy.orm import joinedload
import pdfplumber
import io
from markupsafe import Markup # <-- NOWY IMPORT

bp = Blueprint('finished_goods', __name__, template_folder='templates', url_prefix='/finished_goods')

@bp.route('/')
@login_required
@permission_required('warehouse')
def index():
    categories = FinishedProductCategory.query.options(
        joinedload(FinishedProductCategory.finished_products)
    ).order_by(FinishedProductCategory.name).all()
    return render_template('finished_goods_index.html', categories=categories)

@bp.route('/edit_stock/<int:product_id>', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def edit_product_stock(product_id):
    product = FinishedProduct.query.get_or_404(product_id)
    if request.method == 'POST':
        new_quantity = request.form.get('quantity_in_stock', type=int)
        if new_quantity is not None and new_quantity >= 0:
            product.quantity_in_stock = new_quantity
            db.session.commit()
            flash(f"Zaktualizowano stan magazynowy dla produktu '{product.name}'.", "success")
            return redirect(url_for('finished_goods.index'))
        else:
            flash("Podano nieprawidłową wartość.", "danger")
    
    return render_template('edit_fp_stock.html', product=product)

@bp.route('/import_sales', methods=['GET', 'POST'])
@login_required
@permission_required('warehouse')
def import_sales():
    if request.method == 'POST':
        if 'pdf_file' not in request.files:
            flash('Nie wybrano pliku.', 'warning')
            return redirect(request.url)
        
        file = request.files['pdf_file']
        if file.filename == '':
            flash('Nie wybrano pliku.', 'warning')
            return redirect(request.url)
        
        if file and file.filename.endswith('.pdf'):
            try:
                # === POCZĄTEK ZMIANY: ROZBUDOWA SYSTEMU RAPORTOWANIA ===
                update_details = [] # Lista do przechowywania szczegółów aktualizacji
                not_found_codes = []
                
                with pdfplumber.open(io.BytesIO(file.read())) as pdf:
                    for page in pdf.pages:
                        tables = page.extract_tables()
                        for table in tables:
                            for row in table[1:]:
                                if len(row) > 5 and row[2] and row[5]:
                                    product_code = row[2].strip() # Usuwamy białe znaki
                                    try:
                                        quantity_sold = int(row[5])
                                    except (ValueError, TypeError):
                                        continue
                                    
                                    product = FinishedProduct.query.filter_by(product_code=product_code).first()
                                    
                                    if product:
                                        original_quantity = product.quantity_in_stock
                                        product.quantity_in_stock -= quantity_sold
                                        # Tworzymy szczegółowy opis operacji
                                        details_string = (
                                            f"<b>{product.name}</b> (Kod: {product.product_code}): "
                                            f"{original_quantity} → {product.quantity_in_stock} (-{quantity_sold})"
                                        )
                                        update_details.append(details_string)
                                    else:
                                        if product_code not in not_found_codes:
                                            not_found_codes.append(product_code)
                
                db.session.commit()

                # Przygotowanie komunikatu dla użytkownika
                if update_details:
                    # Łączymy szczegóły w jeden komunikat HTML
                    details_html = "<br>".join(update_details)
                    success_message = Markup(
                        f"<b>Import zakończony. Zaktualizowano {len(update_details)} produktów:</b><br>{details_html}"
                    )
                    flash(success_message, "success")
                else:
                    flash("Nie znaleziono w pliku żadnych produktów do aktualizacji.", "info")

                if not_found_codes:
                    error_message = f"Uwaga: Nie znaleziono w bazie produktów o następujących kodach: {', '.join(not_found_codes)}."
                    flash(error_message, "warning")
                # === KONIEC ZMIANY ===

            except Exception as e:
                db.session.rollback()
                flash(f"Wystąpił błąd podczas przetwarzania pliku PDF: {e}", "danger")
            
            return redirect(url_for('finished_goods.index'))
        else:
            flash('Proszę wybrać plik w formacie PDF.', 'danger')
            return redirect(request.url)

    return render_template('import_sales.html')

@bp.route('/categories', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def manage_categories():
    if request.method == 'POST':
        category_name = request.form.get('name')
        if category_name:
            existing_category = FinishedProductCategory.query.filter_by(name=category_name).first()
            if not existing_category:
                new_category = FinishedProductCategory(name=category_name)
                db.session.add(new_category)
                db.session.commit()
                flash(f"Dodano kategorię: {category_name}", "success")
            else:
                flash("Kategoria o tej nazwie już istnieje.", "warning")
        return redirect(url_for('finished_goods.manage_categories'))
    
    all_categories = FinishedProductCategory.query.order_by(FinishedProductCategory.name).all()
    return render_template('manage_fp_categories.html', categories=all_categories)


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
        flash(f"Nie można usunąć kategorii '{category.name}', ponieważ są do niej przypisane produkty.", "danger")
    else:
        db.session.delete(category)
        db.session.commit()
        flash(f"Kategoria '{category.name}' została usunięta.", "danger")
    return redirect(url_for('finished_goods.manage_categories'))