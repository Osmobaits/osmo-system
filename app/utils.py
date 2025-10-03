from flask import url_for
from flask_login import current_user
from .models import db, ActivityLog

def log_activity(action, url_endpoint=None, **url_params):
    """
    Zapisuje aktywność użytkownika w dzienniku zdarzeń.
    :param action: Opis akcji (string).
    :param url_endpoint: Nazwa endpointu do wygenerowania linku (np. 'orders.order_details').
    :param url_params: Parametry dla url_for (np. id=123).
    """
    if not current_user.is_authenticated:
        return

    log_url = None
    if url_endpoint:
        try:
            log_url = url_for(url_endpoint, **url_params)
        except Exception:
            log_url = None # W razie błędu generowania linku, po prostu go pomijamy

    log_entry = ActivityLog(
        user_id=current_user.id,
        action=action,
        url=log_url
    )
    db.session.add(log_entry)