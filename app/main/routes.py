# app/main/routes.py
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required

bp = Blueprint('main', __name__, template_folder='templates')

@bp.route('/')
@login_required
def index():
    # Przekierowuje na pulpit zadań
    return redirect(url_for('tasks.index'))

@bp.route('/home')
@login_required
def home():
    # Również przekierowuje na pulpit zadań
    return redirect(url_for('tasks.index'))