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
        return render_template('vacations_index.html', 
                               pending_requests=pending_requests,
                               approved_requests=approved_requests)
    else:
        my_requests = VacationRequest.query.filter_by(user_id=current_user.id).order_by(VacationRequest.request_date.desc()).all()
        return render_template('vacations_index.html', my_requests=my_requests)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('vacations')
def create_request():
    if request.method == 'POST':
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        category = request.form.get('category')
        notes = request.form.get('notes')
        new_request = VacationRequest(user_id=current_user.id, start_date=start_date, end_date=end_date, category=category, notes=notes)
        db.session.add(new_request)
        db.session.commit()
        flash('Twój wniosek urlopowy został złożony.', 'success')
        return redirect(url_for('vacations.index'))
    return render_template('create_vacation_request.html')

@bp.route('/admin/create', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def admin_create_request():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        category = request.form.get('category')
        admin_notes = request.form.get('admin_notes')

        new_request = VacationRequest(
            user_id=user_id, 
            start_date=start_date, 
            end_date=end_date, 
            category=category, 
            admin_notes=admin_notes,
            status='Zatwierdzony'
        )
        db.session.add(new_request)
        db.session.commit()
        flash(f'Dodano urlop dla pracownika.', 'success')
        return redirect(url_for('vacations.index'))
    
    employees = User.query.order_by(User.username).all()
    return render_template('admin_create_vacation.html', employees=employees)

@bp.route('/edit/<int:request_id>', methods=['GET', 'POST'])
@login_required
@permission_required('vacations')
def edit_request(request_id):
    req = VacationRequest.query.get_or_404(request_id)
    if req.user_id != current_user.id or req.status != 'Oczekuje':
        flash('Nie można edytować tego wniosku.', 'danger')
        return redirect(url_for('vacations.index'))
    if request.method == 'POST':
        req.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        req.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        req.category = request.form.get('category')
        req.notes = request.form.get('notes')
        db.session.commit()
        flash('Wniosek został zaktualizowany.', 'success')
        return redirect(url_for('vacations.index'))
    return render_template('edit_vacation_request.html', req=req)

@bp.route('/delete/<int:request_id>', methods=['POST'])
@login_required
@permission_required('vacations')
def delete_request(request_id):
    req = VacationRequest.query.get_or_404(request_id)
    if req.user_id != current_user.id or req.status != 'Oczekuje':
        flash('Nie można usunąć tego wniosku.', 'danger')
        return redirect(url_for('vacations.index'))
    db.session.delete(req)
    db.session.commit()
    flash('Wniosek został usunięty.', 'success')
    return redirect(url_for('vacations.index'))

@bp.route('/approve/<int:request_id>', methods=['POST'])
@login_required
@permission_required('admin')
def approve_request(request_id):
    vacation_request = VacationRequest.query.get_or_404(request_id)
    vacation_request.status = 'Zatwierdzony'
    vacation_request.admin_notes = request.form.get('admin_notes')
    db.session.commit()
    flash(f'Wniosek urlopowy dla {vacation_request.user.username} został zatwierdzony.', 'success')
    return redirect(url_for('vacations.index'))

@bp.route('/reject/<int:request_id>', methods=['POST'])
@login_required
@permission_required('admin')
def reject_request(request_id):
    vacation_request = VacationRequest.query.get_or_404(request_id)
    vacation_request.status = 'Odrzucony'
    vacation_request.admin_notes = request.form.get('admin_notes')
    db.session.commit()
    flash(f'Wniosek urlopowy dla {vacation_request.user.username} został odrzucony.', 'warning')
    return redirect(url_for('vacations.index'))

@bp.route('/admin/edit/<int:request_id>', methods=['GET', 'POST'])
@login_required
@permission_required('admin')
def admin_edit_request(request_id):
    req = VacationRequest.query.get_or_404(request_id)
    if request.method == 'POST':
        req.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        req.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        req.category = request.form.get('category')
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
    flash('Wniosek urlopowy został trwale usunięty.', 'success')
    return redirect(url_for('vacations.index'))