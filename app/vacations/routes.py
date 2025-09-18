# app/vacations/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, VacationRequest, User
from flask_login import login_required, current_user
from app.decorators import permission_required
from datetime import datetime

bp = Blueprint('vacations', __name__, template_folder='templates', url_prefix='/vacations')

@bp.route('/')
@login_required
@permission_required('vacations')
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

@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('vacations')
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

@bp.route('/edit/<int:request_id>', methods=['GET', 'POST'])
@login_required
@permission_required('vacations')
def edit_request(request_id):
    req = VacationRequest.query.get_or_404(request_id)
    if req.user_id != current_user.id:
        flash('Brak uprawnień do edycji tego wniosku.', 'danger')
        return redirect(url_for('vacations.index'))
    if req.status != 'Oczekuje':
        flash('Nie można edytować wniosku, który został już rozpatrzony.', 'warning')
        return redirect(url_for('vacations.index'))

    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        notes = request.form.get('notes')
        if not start_date_str or not end_date_str:
            flash('Obie daty są wymagane.', 'danger')
            return redirect(url_for('vacations.edit_request', request_id=req.id))
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        if start_date > end_date:
            flash('Data końcowa nie może być wcześniejsza niż data początkowa.', 'danger')
            return redirect(url_for('vacations.edit_request', request_id=req.id))
        req.start_date = start_date
        req.end_date = end_date
        req.notes = notes
        db.session.commit()
        flash('Wniosek urlopowy został zaktualizowany.', 'success')
        return redirect(url_for('vacations.index'))
    return render_template('edit_vacation_request.html', req=req)

@bp.route('/delete/<int:request_id>', methods=['POST'])
@login_required
@permission_required('vacations')
def delete_request(request_id):
    req = VacationRequest.query.get_or_404(request_id)
    if req.user_id != current_user.id:
        flash('Brak uprawnień do usunięcia tego wniosku.', 'danger')
        return redirect(url_for('vacations.index'))
    if req.status != 'Oczekuje':
        flash('Nie można usunąć wniosku, który został już rozpatrzony.', 'warning')
        return redirect(url_for('vacations.index'))
    db.session.delete(req)
    db.session.commit()
    flash('Wniosek urlopowy został usunięty.', 'success')
    return redirect(url_for('vacations.index'))

@bp.route('/<int:request_id>/approve', methods=['POST'])
@login_required
@permission_required('admin')
def approve_request(request_id):
    vacation_request = VacationRequest.query.get_or_404(request_id)
    vacation_request.status = 'Zatwierdzony'
    vacation_request.admin_notes = request.form.get('admin_notes', '')
    db.session.commit()
    flash(f'Wniosek urlopowy dla {vacation_request.user.username} został zatwierdzony.', 'success')
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

# === POCZĄTEK NOWEJ SEKCJI: EDYCJA I USUWANIE PRZEZ ADMINA ===
@bp.route('/admin/edit/<int:request_id>', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def admin_edit_request(request_id):
    req = VacationRequest.query.get_or_404(request_id)
    if request.method == 'POST':
        req.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        req.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        req.notes = request.form.get('notes')
        req.admin_notes = request.form.get('admin_notes')
        req.status = request.form.get('status')
        db.session.commit()
        flash('Wniosek urlopowy został zaktualizowany przez administratora.', 'success')
        return redirect(url_for('vacations.index'))
    return render_template('admin_edit_vacation_request.html', req=req)

@bp.route('/admin/delete/<int:request_id>', methods=['POST'])
@login_required
@permission_required('admin')
def admin_delete_request(request_id):
    req = VacationRequest.query.get_or_404(request_id)
    db.session.delete(req)
    db.session.commit()
    flash(f'Wniosek urlopowy dla {req.user.username} został trwale usunięty.', 'success')
    return redirect(url_for('vacations.index'))
# === KONIEC NOWEJ SEKCJI ===