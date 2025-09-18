# app/reports/routes.py
from flask import Blueprint, render_template, Response
from app.models import FinishedProductCategory, Category, PackagingCategory, RawMaterial
from flask_login import login_required
from sqlalchemy.orm import joinedload
from weasyprint import HTML

bp = Blueprint('reports', __name__, template_folder='templates', url_prefix='/reports')

@bp.route('/inventory_sheet')
@login_required
def inventory_sheet_pdf():
    # Pobieranie danych
    finished_product_categories = FinishedProductCategory.query.options(
        joinedload(FinishedProductCategory.finished_products)
    ).order_by(FinishedProductCategory.name).all()

    raw_material_categories = Category.query.options(
        joinedload(Category.raw_materials).joinedload(RawMaterial.batches)
    ).order_by(Category.name).all()

    packaging_categories = PackagingCategory.query.options(
        joinedload(PackagingCategory.packaging_items)
    ).order_by(PackagingCategory.name).all()

    # Renderowanie szablonu HTML
    rendered_html = render_template('inventory_sheet.html',
                                    finished_product_categories=finished_product_categories,
                                    raw_material_categories=raw_material_categories,
                                    packaging_categories=packaging_categories)

    # Tworzenie PDF
    pdf = HTML(string=rendered_html).write_pdf()

    return Response(pdf,
                    mimetype='application/pdf',
                    headers={'Content-Disposition': 'attachment;filename=inwentaryzacja.pdf'})