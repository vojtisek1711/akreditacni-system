import os
import uuid
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, flash, abort
import qrcode
from pathlib import Path
from functools import wraps

# ========== Flask App ========== #
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tajnyklic")

DATABASE = "data.db"
UPLOAD_FOLDER = "uploads"
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "adminvstup")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5001")


# ========== Databáze ========== #
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS accreditations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT UNIQUE,
                active INTEGER,
                filename TEXT,
                created TIMESTAMP
            )
        """)
init_db()


# ========== Helpers ========== #
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


def generate_qr(uuid_value):
    qr_url = f"{BASE_URL}/a/{uuid_value}"
    img = qrcode.make(qr_url)
    qr_path = Path(UPLOAD_FOLDER) / f"{uuid_value}.png"
    img.save(qr_path)
    return qr_path.name


# ========== Routes veřejné ========== #
@app.route("/")
def home():
