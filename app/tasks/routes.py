# app/tasks/routes.py
import os
import json
import time
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, Response, g, send_from_directory
from app.models import db, User, Task, TaskAttachment
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.decorators import permission_required
from flask_mail import Message
from app import mail

bp = Blueprint('tasks', __name__, template_folder='templates', url_prefix='/tasks')

@bp.route('/stream')
@login_required
def stream():
    def event_stream():
        while True:
            time.sleep(60)
            yield "data: heartbeat\n\n"
    return Response(event_stream(), mimetype='text/event-stream')

@bp.route('/')
@login_required
@permission_required('tasks')
def index():
    tasks_assigned_to_me = Task.query.filter(Task.assignees.contains(current_user), Task.status != 'Zakończone').order_by(Task.creation_date.desc()).all()
    tasks_created_by_me = Task.query.filter(Task.assigner_id == current_user.id, Task.status != 'Zakończone').order_by(Task.creation_date.desc()).all()
    return render_template('tasks_list.html', assigned_tasks=tasks_assigned_to_me, created_tasks=tasks_created_by_me)

@bp.route('/archive')
@login_required
@permission_required('tasks')
def archive():
    completed_tasks = Task.query.filter(
        db.or_(Task.assignees.contains(current_user), Task.assigner_id == current_user.id),
        Task.status == 'Zakończone'
    ).order_by(Task.creation_date.desc()).all()
    return render_template('tasks_archive.html', tasks=completed_tasks)

@bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('tasks')
def create_task():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        assignee_ids = request.form.getlist('assignee_ids', type=int)
        priority = request.form.get('priority')
        due_date_str = request.form.get('due_date')
        files = request.files.getlist('attachments')
        if not title or not assignee_ids:
            flash("Tytuł i przynajmniej jeden pracownik są wymagane.", "warning")
            return redirect(url_for('tasks.create_task'))
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
        new_task = Task(
            title=title, description=description, assigner_id=current_user.id,
            priority=int(priority), due_date=due_date
        )
        assignees = User.query.filter(User.id.in_(assignee_ids)).all()
        new_task.assignees.extend(assignees)
        db.session.add(new_task)
        for file in files:
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                attachment = TaskAttachment(task=new_task, filename=filename, filepath=filename)
                db.session.add(attachment)
        db.session.commit()
        try:
            for assignee in assignees:
                if assignee.email:
                    msg = Message(f"Nowe zadanie w systemie: {new_task.title}", recipients=[assignee.email])
                    msg.body = f"Cześć {assignee.username},\n\nPrzypisano Ci nowe zadanie: \"{new_task.title}\"."
                    mail.send(msg)
            flash("Zadanie zostało utworzone, a pracownicy poinformowani.", "success")
        except Exception as e:
            flash(f"Zadanie utworzono, ale wystąpił błąd przy wysyłce e-maili: {e}", "danger")
        return redirect(url_for('tasks.index'))
    users = User.query.order_by(User.username).all()
    return render_template('create_task.html', users=users)

@bp.route('/<int:id>')
@login_required
@permission_required('tasks')
def task_details(id):
    task = Task.query.get_or_404(id)
    if task.assigner_id != current_user.id and current_user not in task.assignees and not current_user.has_role('admin'):
        flash("Nie masz uprawnień do tego zadania.", "danger")
        return redirect(url_for('tasks.index'))
    return render_template('task_details.html', task=task)

@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('tasks')
def edit_task(id):
    task = Task.query.get_or_404(id)
    if task.assigner_id != current_user.id and not current_user.has_role('admin'):
        flash("Nie masz uprawnień do edycji tego zadania.", "danger")
        return redirect(url_for('tasks.index'))
    if request.method == 'POST':
        task.title = request.form.get('title')
        task.description = request.form.get('description')
        assignee_ids = request.form.getlist('assignee_ids', type=int)
        task.priority = int(request.form.get('priority'))
        due_date_str = request.form.get('due_date')
        task.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None
        assignees = User.query.filter(User.id.in_(assignee_ids)).all()
        task.assignees = assignees
        db.session.commit()
        flash("Zadanie zostało zaktualizowane.", "success")
        return redirect(url_for('tasks.task_details', id=task.id))
    users = User.query.order_by(User.username).all()
    return render_template('edit_task.html', task=task, users=users)

@bp.route('/<int:id>/accept', methods=['POST'])
@login_required
@permission_required('tasks')
def accept_task(id):
    task = Task.query.get_or_404(id)
    if current_user in task.assignees and task.status == 'Nowe':
        task.status = 'Przyjęte'
        db.session.commit()
        flash("Potwierdzono odbiór zadania.", "info")
    else:
        flash("Nie możesz wykonać tej akcji.", "warning")
    return redirect(url_for('tasks.task_details', id=id))

@bp.route('/<int:id>/complete', methods=['POST'])
@login_required
@permission_required('tasks')
def complete_task(id):
    task = Task.query.get_or_404(id)
    if current_user in task.assignees and task.status == 'Przyjęte':
        task.status = 'Zakończone'
        db.session.commit()
        flash("Zadanie zostało oznaczone jako zakończone.", "success")
    else:
        flash("Nie możesz wykonać tej akcji.", "warning")
    return redirect(url_for('tasks.task_details', id=id))
    
@bp.route('/download/<path:filename>')
@login_required
@permission_required('tasks')
def download_file(filename):
    safe_path = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
    return send_from_directory(safe_path, filename, as_attachment=True)

# === PRZYWRÓCONA FUNKCJA: WYSYŁANIE PRZYPOMNIENIA ===
@bp.route('/<int:id>/remind', methods=['POST'])
@login_required
@permission_required('tasks')
def remind_task(id):
    task = Task.query.get_or_404(id)
    if current_user.id == task.assigner_id or current_user.has_role('admin'):
        try:
            for assignee in task.assignees:
                if assignee.email:
                    msg = Message(f"Przypomnienie o zadaniu: {task.title}", recipients=[assignee.email])
                    msg.body = f"Cześć {assignee.username},\n\nTo jest przypomnienie o zadaniu \"{task.title}\", które zostało Ci zlecone przez {task.assigner.username}.\n\nTermin realizacji: {task.due_date.strftime('%Y-%m-%d') if task.due_date else 'Brak'}\n\nProsimy o podjęcie działań."
                    mail.send(msg)
            flash("Przypomnienia e-mail zostały wysłane do pracowników.", "success")
        except Exception as e:
            flash(f"Nie udało się wysłać przypomnień. Błąd: {e}", "danger")
    else:
        flash("Nie masz uprawnień do wysyłania przypomnień dla tego zadania.", "danger")
    
    return redirect(url_for('tasks.task_details', id=id))