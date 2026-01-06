#!/bin/bash
set -o errexit
pip install -r requirements.txt
# Ta linia naprawi wersję w bazie Postgres na Renderze:
flask shell -c "from app.models import db; db.session.execute(db.text(\"UPDATE alembic_version SET version_num = '60da692b8fb2'\")); db.session.commit()"
flask db upgrade