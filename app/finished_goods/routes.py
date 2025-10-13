from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, FinishedProduct, FinishedProductCategory, SalesReportLog
from flask_login import login_required
from app.decorators import permission_required
from sqlalchemy import asc, desc
from markupsafe import Markup
import pdfplumber
import io
import re
from datetime import datetime

bp = Blueprint('finished_goods', __name__, template_folder='templates', url_prefix='/finished_goods')

@bp.route('/')
@login_required
@permission_required('warehouse')
def index():
    categories = FinishedProductCategory.query.order_by(FinishedProductCategory.name).all()
    sort_by = request.args.get('sort_by', 'name')
    order = request.args.get('order', 'asc')

    sort_map = {'name': FinishedProduct.name, 'quantity': FinishedProduct.quantity_in_stock}
    sort_column = sort_map.get(sort_by, FinishedProduct.name)

    query = FinishedProduct.query.order_by(asc(sort_column) if order == 'asc' else desc(sort_column))
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
            if not FinishedProductCategory.query.filter_by(name=name).first():
                db.session.add(FinishedProductCategory(name=name))
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
        if 'pdf_file' not in request.files:
            flash('Nie wybrano pliku.', 'danger')
            return redirect(request.url)
        file = request.files['pdf_file']
        if file.filename == '':
            flash('Nie wybrano pliku.', 'danger')
            return redirect(request.url)
        if file and file.filename.endswith('.pdf'):
            try:
                pdf_stream = io.BytesIO(file.read())
                with pdfplumber.open(pdf_stream) as pdf:
                    text = "".join(page.extract_text() for page in pdf.pages)
                    
                    # --- POPRAWKA TUTAJ ---
                    # Szukamy nowej frazy "ZA OKRES:"
                    date_match = re.search(r'ZA OKRES:\s*(\d{4}-\d{2}-\d{2})', text)
                    # ----------------------

                    if not date_match:
                        flash('Nie można znaleźć daty raportu w pliku PDF. Upewnij się, że zawiera frazę "ZA OKRES: RRRR-MM-DD".', 'danger')
                        return redirect(url_for('finished_goods.index'))
                    report_date = datetime.strptime(date_match.group(1), '%Y-%m-%d').date()

                    updated_products = []
                    not_found_codes = []

                    for page in pdf.pages:
                        tables = page.extract_tables()
                        for table in tables:
                            # Szukamy nagłówka tabeli, aby zidentyfikować właściwe kolumny
                            try:
                                header = [h.replace('\n', ' ') if h else '' for h in table[0]]
                                code_idx = header.index('Kod produktu')
                                qty_idx = header.index('Ilość sprzedana')
                            except (ValueError, IndexError):
                                continue # To nie jest tabela, której szukamy

                            for row in table[1:]: # Iterujemy od drugiego wiersza (pomijamy nagłówek)
                                if len(row) > max(code_idx, qty_idx) and row[code_idx]:
                                    product_code = row[code_idx].strip()
                                    try:
                                        quantity_sold = int(row[qty_idx])
                                    except (ValueError, TypeError):
                                        continue

                                    products = FinishedProduct.query.filter_by(product_code=product_code).all()
                                    if not products:
                                        if product_code not in not_found_codes:
                                            not_found_codes.append(product_code)
                                        continue

                                    for product in products:
                                        log_entry = SalesReportLog.query.filter_by(
                                            product_id=product.id,
                                            report_date=report_date
                                        ).first()
                                        
                                        quantity_to_deduct = 0
                                        if log_entry:
                                            quantity_to_deduct = quantity_sold - log_entry.quantity_sold
                                            log_entry.quantity_sold = quantity_sold
                                        else:
                                            quantity_to_deduct = quantity_sold
                                            new_log = SalesReportLog(
                                                product_id=product.id,
                                                report_date=report_date,
                                                quantity_sold=quantity_sold
                                            )
                                            db.session.add(new_log)
                                        
                                        if quantity_to_deduct > 0:
                                            product.quantity_in_stock -= quantity_to_deduct
                                            updated_products.append({'name': product.name, 'deducted': quantity_to_deduct})

                    db.session.commit()
                    
                    msg = f"Import zakończony dla raportu z dnia {report_date.strftime('%Y-%m-%d')}.<br>"
                    if updated_products:
                        updated_names = list(set([p['name'] for p in updated_products]))
                        msg += "Zaktualizowano stany dla: " + ", ".join(updated_names) + "."
                    if not_found_codes:
                        msg += "<br><b>Nie znaleziono produktów o kodach:</b> " + ", ".join(not_found_codes)
                    
                    flash(Markup(msg), 'success')

            except Exception as e:
                flash(f'Wystąpił błąd podczas przetwarzania pliku PDF: {e}', 'danger')

            return redirect(url_for('finished_goods.index'))

    return render_template('import_sales.html')