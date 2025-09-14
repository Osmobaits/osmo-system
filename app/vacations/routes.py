# app/vacations/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, VacationRequest, User
from flask_login import login_required, current_user
from app.decorators import permission_required
from datetime import datetime

bp = Blueprint('vacations', __name__, template_folder='templates', url_prefix='/vacations')

# === POCZĄTEK ZMIANY: DODANIE DEKORATORA ===
@bp.route('/')
@login_required
@permission_required('vacations')
# === KONIEC ZMIANY ===
def index():
    if current_user.has_role('admin'):
        pending_requests = VacationRequest.query.filter_by(status='Oczekuje').order_by(VacationRequest.request_date.desc()).all()
        approved_requests = VacationRequest.query.filter_by(status='Zatwierdzony').order_by(VacationRequest.start_date.desc()).all()
        rejected_requests = VacationRequest.query.filter_by(status='Odrzucony').order_by(VacationRequest.request_date.desc()).all()
        return render_template('vacations_index.html', 
                               pending_requests=pending_requests,
                               approved_requests=approved_requests,
                               rejected_requests=rejected_requests)
    else:
        my_requests = VacationRequest.query.filter_by(user_id=current_user.id).order_by(VacationRequest.request_date.desc()).all()
        return render_template('vacations_index.html', my_requests=my_requests)

# === POCZĄTEK ZMIANY: DODANIE DEKORATORA ===
@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('vacations')
# === KONIEC ZMIANY ===
def create_request():
    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        notes = request.form.get('notes')

        if not start_date_str or not end_date_str:
            flash('Obie daty są wymagane.', 'danger')
            return redirect(url_for('vacations.create_request'))

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        if start_date > end_date:
            flash('Data końcowa nie może być wcześniejsza niż data początkowa.', 'danger')
            return redirect(url_for('vacations.create_request'))

        new_request = VacationRequest(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            notes=notes
        )
        db.session.add(new_request)
        db.session.commit()
        flash('Twój wniosek urlopowy został pomyślnie złożony.', 'success')
        return redirect(url_for('vacations.index'))

    return render_template('create_vacation_request.html')

@bp.route('/<int:request_id>/approve', methods=['POST'])
@login_required
@permission_required('admin')
def approve_request(request_id):
    vacation_request = VacationRequest.query.get_or_404(request_id)
    vacation_request.status = 'Zatwierdzony'
    vacation_request.admin_notes = request.form.get('admin_notes', '')
    db.session.commit()
    flash(f'Wnioseok urlopowy dla {vacation_request.user.username} został zatwierdzony.', 'success')
    return redirect(url_for('vacations.index'))

@bp.route('/<int:request_id>/reject', methods=['POST'])
@login_required
@permission_required('admin')
def reject_request(request_id):
    vacation_request = VacationRequest.query.get_or_404(request_id)
    vacation_request.status = 'Odrzucony'
    vacation_request.admin_notes = request.form.get('admin_notes', '')
    db.session.commit()
    flash(f'Wniosek urlopowy dla {vacation_request.user.username} został odrzucony.', 'warning')
    return redirect(url_for('vacations.index'))