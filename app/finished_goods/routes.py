# app/finished_goods/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, FinishedProductCategory, FinishedProduct, SalesReportLog
from flask_login import login_required
from app.decorators import permission_required
from sqlalchemy.orm import joinedload
import pdfplumber
import io
import re
from datetime import datetime
from markupsafe import Markup

bp = Blueprint('finished_goods', __name__, template_folder='templates', url_prefix='/finished_goods')

@bp.route('/')
@login_required
@permission_required('warehouse') # Używamy uprawnienia warehouse
def index():
    categories = FinishedProductCategory.query.order_by(FinishedProductCategory.name).all()

    # Wyszukaj produkty poniżej stanu krytycznego
    low_stock_products = FinishedProduct.query.filter(
        FinishedProduct.quantity_in_stock < FinishedProduct.critical_stock_level,
        FinishedProduct.critical_stock_level > 0
    ).all()

    return render_template('finished_goods_index.html', categories=categories, low_stock_products=low_stock_products)

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

# === POCZĄTEK PRZEBUDOWY: LOGIKA FIFO DLA ZDUPLIKOWANYCH KODÓW ===
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
                update_details = []
                not_found_codes = []
                report_date = None

                pdf_content = io.BytesIO(file.read())
                with pdfplumber.open(pdf_content) as pdf:
                    first_page_text = pdf.pages[0].extract_text()
                    date_match = re.search(r'ZA OKRES: (\d{4}-\d{2}-\d{2})', first_page_text)
                    if date_match:
                        report_date = datetime.strptime(date_match.group(1), '%Y-%m-%d').date()
                    else:
                        flash("Nie udało się odnaleźć daty w raporcie PDF. Przerwano.", "danger")
                        return redirect(url_for('finished_goods.index'))

                    for page in pdf.pages:
                        tables = page.extract_tables()
                        for table in tables:
                            for row in table[1:]:
                                if len(row) > 5 and row[2] and row[5]:
                                    product_code = row[2].strip() if row[2] else None
                                    if not product_code: continue

                                    try:
                                        current_quantity_sold = int(row[5])
                                    except (ValueError, TypeError):
                                        continue

                                    # Znajdujemy WSZYSTKIE produkty z danym kodem
                                    products = FinishedProduct.query.filter_by(product_code=product_code).order_by(FinishedProduct.id).all()
                                    
                                    if products:
                                        # Sprawdzamy dziennik importów dla pierwszego znalezionego produktu (zakładamy, że log jest per kod)
                                        log_entry = SalesReportLog.query.filter_by(
                                            product_id=products[0].id,
                                            report_date=report_date
                                        ).first()
                                        
                                        last_logged_quantity = log_entry.quantity_sold if log_entry else 0
                                        quantity_to_deduct = current_quantity_sold - last_logged_quantity

                                        if quantity_to_deduct > 0:
                                            remaining_to_deduct = quantity_to_deduct
                                            for product in products:
                                                if remaining_to_deduct <= 0: break
                                                
                                                deduction_amount = min(product.quantity_in_stock, remaining_to_deduct)
                                                if deduction_amount > 0:
                                                    original_stock = product.quantity_in_stock
                                                    product.quantity_in_stock -= deduction_amount
                                                    remaining_to_deduct -= deduction_amount
                                                    
                                                    details_string = (
                                                        f"<b>{product.name}</b> (Kod: {product.product_code}): "
                                                        f"{original_stock} → {product.quantity_in_stock} (-{deduction_amount})"
                                                    )
                                                    update_details.append(details_string)
                                        
                                        # Zaktualizuj lub stwórz nowy wpis w dzienniku
                                        if log_entry:
                                            log_entry.quantity_sold = current_quantity_sold
                                        else:
                                            new_log_entry = SalesReportLog(
                                                product_id=products[0].id,
                                                report_date=report_date,
                                                quantity_sold=current_quantity_sold
                                            )
                                            db.session.add(new_log_entry)
                                    else:
                                        if product_code not in not_found_codes:
                                            not_found_codes.append(product_code)
                
                db.session.commit()

                if update_details:
                    details_html = "<br>".join(update_details)
                    success_message = Markup(
                        f"<b>Import dla dnia {report_date.strftime('%Y-%m-%d')} zakończony. Zaktualizowano {len(update_details)} pozycji:</b><br>{details_html}"
                    )
                    flash(success_message, "success")
                else:
                    flash(f"Import dla dnia {report_date.strftime('%Y-%m-%d')} zakończony. Brak nowych sprzedaży do odnotowania.", "info")

                if not_found_codes:
                    error_message = f"Uwaga: Nie znaleziono w bazie produktów o następujących kodach: {', '.join(not_found_codes)}."
                    flash(error_message, "warning")

            except Exception as e:
                db.session.rollback()
                flash(f"Wystąpił krytyczny błąd podczas przetwarzania pliku PDF: {e}", "danger")
            
            return redirect(url_for('finished_goods.index'))
        else:
            flash('Proszę wybrać plik w formacie PDF.', 'danger')
            return redirect(request.url)

    return render_template('import_sales.html')
# === KONIEC PRZEBUDOWY ===

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