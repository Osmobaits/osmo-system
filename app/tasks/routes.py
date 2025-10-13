import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory
from app.models import db, User, Task, TaskAttachment, Role
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.decorators import permission_required
from flask_mail import Message
from app import mail
from app.utils import log_activity

bp = Blueprint('tasks', __name__, template_folder='templates', url_prefix='/tasks')

@bp.route('/')
@login_required
@permission_required('tasks')
def index():
    tasks_assigned_to_me = Task.query.filter(Task.assignees.contains(current_user), Task.status != 'Zakończone').order_by(Task.creation_date.desc()).all()
    tasks_created_by_me = Task.query.filter(Task.assigner_id == current_user.id, Task.status != 'Zakończone').order_by(Task.creation_date.desc()).all()
    return render_template('tasks_list.html', assigned_tasks=tasks_assigned_to_me, created_tasks=tasks_created_by_me)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('tasks')
def create_task():
    if current_user.has_role('team_member') and not current_user.has_role('admin'):
        flash('Członkowie drużyny nie mogą tworzyć nowych zadań.', 'danger')
        return redirect(url_for('tasks.index'))

    if request.method == 'POST':
        # ... (logika tworzenia zadania, bez zmian)
        title = request.form.get('title')
        description = request.form.get('description')
        priority = request.form.get('priority', type=int)
        due_date_str = request.form.get('due_date')
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
        assignee_ids = request.form.getlist('assignee_ids')
        files = request.files.getlist('attachments')

        if not title or not assignee_ids:
            flash('Tytuł i przynajmniej jeden adresat są wymagane.', 'warning')
            return redirect(url_for('tasks.create_task'))
            
        assignees = User.query.filter(User.id.in_(assignee_ids)).all()
        
        new_task = Task(title=title, description=description, priority=priority, due_date=due_date, assigner_id=current_user.id, assignees=assignees)
        db.session.add(new_task)
        
        for file in files:
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                unique_filename = f"{datetime.utcnow().timestamp()}_{filename}"
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                
                attachment = TaskAttachment(task=new_task, filename=filename, filepath=unique_filename)
                db.session.add(attachment)

        db.session.commit()
        assignee_names = ", ".join([u.username for u in assignees])
        log_activity(f"Utworzył nowe zadanie: '{new_task.title}' dla: {assignee_names}", 'tasks.task_details', id=new_task.id)
        flash('Pomyślnie utworzono zadanie.', 'success')
        return redirect(url_for('tasks.index'))
        
    # Logika filtrowania listy użytkowników
    if current_user.has_role('admin'):
        users = User.query.order_by(User.username).all()
    else:
        team_member_role = Role.query.filter_by(name='team_member').first()
        admin_role = Role.query.filter_by(name='admin').first()
        if team_member_role and admin_role:
            pure_team_members_subquery = db.session.query(User.id).filter(User.roles.any(id=team_member_role.id), ~User.roles.any(id=admin_role.id))
            users = User.query.filter(User.id.not_in(pure_team_members_subquery)).order_by(User.username).all()
        else:
            users = User.query.order_by(User.username).all()
    
    return render_template('create_task.html', users=users)
    
@bp.route('/<int:id>')
@login_required
@permission_required('tasks')
def task_details(id):
    task = Task.query.get_or_404(id)
    return render_template('task_details.html', task=task)

@bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@permission_required('tasks')
def edit_task(id):
    # ... (cała funkcja edycji pozostaje bez zmian)
    task = Task.query.get_or_404(id)
    if task.assigner_id != current_user.id and not current_user.has_role('admin'):
        flash('Nie masz uprawnień do edycji tego zadania.', 'danger')
        return redirect(url_for('tasks.task_details', id=id))

    if request.method == 'POST':
        task.title = request.form.get('title')
        task.description = request.form.get('description')
        task.priority = request.form.get('priority', type=int)
        due_date_str = request.form.get('due_date')
        task.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
        
        assignee_ids = request.form.getlist('assignee_ids')
        task.assignees = User.query.filter(User.id.in_(assignee_ids)).all()
        
        db.session.commit()
        flash('Zadanie zostało zaktualizowane.', 'success')
        return redirect(url_for('tasks.task_details', id=id))
    
    if current_user.has_role('admin'):
        users = User.query.order_by(User.username).all()
    else:
        team_member_role = Role.query.filter_by(name='team_member').first()
        admin_role = Role.query.filter_by(name='admin').first()
        if team_member_role and admin_role:
            pure_team_members_subquery = db.session.query(User.id).filter(User.roles.any(id=team_member_role.id), ~User.roles.any(id=admin_role.id))
            users = User.query.filter(User.id.not_in(pure_team_members_subquery)).order_by(User.username).all()
        else:
            users = User.query.order_by(User.username).all()
            
    return render_template('edit_task.html', task=task, users=users)

@bp.route('/archive')
@login_required
@permission_required('tasks')
def archive():
    tasks = Task.query.filter_by(status='Zakończone').order_by(Task.creation_date.desc()).all()
    return render_template('tasks_archive.html', tasks=tasks)

# --- POCZĄTEK POPRAWKI ---
@bp.route('/<int:id>/accept', methods=['POST'])
@login_required
# Usunęliśmy @permission_required('tasks')
def accept_task(id):
    task = Task.query.get_or_404(id)
    
    # Dodajemy szczegółową weryfikację uprawnień wewnątrz funkcji
    if current_user not in task.assignees:
        flash('Brak uprawnień do wykonania tej akcji.', 'danger')
        return redirect(url_for('tasks.task_details', id=id))

    if task.status == 'Nowe':
        task.status = 'Przyjęte'
        db.session.commit()
        flash('Zadanie zostało przyjęte do realizacji.', 'info')
    else:
        flash(f"Nie można przyjąć zadania, ponieważ ma ono już status '{task.status}'.", "warning")
        
    return redirect(url_for('tasks.task_details', id=id))

@bp.route('/<int:id>/complete', methods=['POST'])
@login_required
# Usunęliśmy @permission_required('tasks')
def complete_task(id):
    task = Task.query.get_or_404(id)
    
    # Używamy już istniejącej, dobrej logiki weryfikacji
    if current_user in task.assignees or current_user.id == task.assigner_id or current_user.has_role('admin'):
        task.status = 'Zakończone'
        db.session.commit()
        log_activity(f"Zakończył zadanie: '{task.title}'", 'tasks.task_details', id=task.id)
        flash('Zadanie zostało oznaczone jako zakończone.', 'success')
    else:
        flash("Brak uprawnień do wykonania tej akcji.", "danger")
        
    return redirect(url_for('tasks.task_details', id=id))
# --- KONIEC POPRAWKI ---
    
@bp.route('/download/<path:filename>')
@login_required
@permission_required('tasks')
def download_file(filename):
    safe_path = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
    return send_from_directory(safe_path, filename, as_attachment=True)

@bp.route('/<int:id>/remind', methods=['POST'])
@login_required
@permission_required('tasks')
def remind_task(id):
    # ... (cała funkcja remind bez zmian)
    task = Task.query.get_or_404(id)
    if current_user.id == task.assigner_id or current_user.has_role('admin'):
        try:
            for assignee in task.assignees:
                if assignee.email:
                    msg = Message(f"Przypomnienie o zadaniu: {task.title}", recipients=[assignee.email])
                    msg.body = f"Cześć {assignee.username},\n\nTo jest przypomnienie o zadaniu \"{task.title}\", które zostało Ci zlecone przez {task.assigner.username}.\n\nTermin realizacji: {task.due_date.strftime('%Y-%m-%d') if task.due_date else 'Brak'}\n\nProsimy o podjęcie działań."
                    mail.send(msg)
            flash("Przypomnienia e-mail zostały wysłane.", "success")
        except Exception as e:
            flash(f"Wystąpił błąd podczas wysyłania e-maili: {e}", "danger")
    else:
        flash("Nie masz uprawnień, aby wysłać przypomnienia.", "danger")
    return redirect(url_for('tasks.task_details', id=id))
    
@bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@permission_required('admin') # Tylko admin może kasować zadania
def delete_task(id):
    """Trwale usuwa zadanie wraz z jego załącznikami."""
    task_to_delete = Task.query.get_or_404(id)

    # 1. Usuń fizyczne pliki załączników z serwera
    for attachment in task_to_delete.attachments:
        try:
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], attachment.filepath)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            # Jeśli pliku nie ma, po prostu zignoruj błąd i kontynuuj
            print(f"Błąd podczas usuwania pliku {attachment.filepath}: {e}")

    # 2. Usuń zadanie z bazy danych
    # (Załączniki zostaną usunięte automatycznie dzięki 'cascade="all, delete-orphan"')
    db.session.delete(task_to_delete)
    db.session.commit()

    log_activity(f"Trwale usunął zadanie: '{task_to_delete.title}'")

    flash(f"Zadanie '{task_to_delete.title}' zostało trwale usunięte.", 'success')

    # Przekieruj na listę zadań lub do archiwum, w zależności skąd przyszliśmy
    if 'archive' in request.referrer:
        return redirect(url_for('tasks.archive'))
    return redirect(url_for('tasks.index'))