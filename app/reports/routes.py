from flask import Blueprint, render_template, Response
from app.models import db, FinishedProductCategory, Category, PackagingCategory, RawMaterial, TeamOrder, TeamOrderProduct
from flask_login import login_required
from sqlalchemy.orm import joinedload
from weasyprint import HTML
from datetime import datetime
from app.decorators import permission_required # <-- DODAJ TEN IMPORT

bp = Blueprint('reports', __name__, template_folder='templates', url_prefix='/reports')

@bp.route('/inventory_sheet')
@login_required
@permission_required('admin') # Zakładając, że admin ma dostęp
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

    generation_time = datetime.now()

    rendered_html = render_template('inventory_sheet.html',
                                    finished_product_categories=finished_product_categories,
                                    raw_material_categories=raw_material_categories,
                                    packaging_categories=packaging_categories,
                                    generation_time=generation_time)

    pdf = HTML(string=rendered_html).write_pdf()

    return Response(pdf,
                    mimetype='application/pdf',
                    headers={'Content-Disposition': 'attachment;filename=inwentaryzacja.pdf'})


@bp.route('/team_order_pdf/<int:order_id>')
@login_required
@permission_required('admin')
def team_order_pdf(order_id):
    order = TeamOrder.query.options(
        joinedload(TeamOrder.user),
        joinedload(TeamOrder.products).joinedload(TeamOrderProduct.product)
    ).get_or_404(order_id)
    
    generation_time = datetime.now()
    
    rendered_html = render_template('team_order_sheet.html', 
                                    order=order, 
                                    generation_time=generation_time)
    
    pdf = HTML(string=rendered_html).write_pdf()
    
    return Response(
        pdf,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment;filename=zamowienie_druzynowe_{order.id}.pdf'}
    )