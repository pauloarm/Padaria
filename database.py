import sqlite3
from flask import g

DATABASE = 'vendas.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._databse = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db(app):
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()