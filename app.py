#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import uuid
import sqlite3
from datetime import datetime
from pathlib import Path
from functools import wraps

from flask import (
    Flask, request, redirect, url_for, render_template_string, send_from_directory,
    session, flash, abort
)
from jinja2 import DictLoader
import qrcode

# ==================== Nastavení ====================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "app.db"

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")  # když není, vytvoří se admin/admin
SECRET_KEY  = os.environ.get("SECRET_KEY", os.urandom(24))

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "pdf"}

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ==================== Pomocné funkce ====================
def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = get_db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    );""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS companies(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        slug TEXT UNIQUE NOT NULL
    );""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS accreditations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT UNIQUE NOT NULL,
        company_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        filename TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY(company_id) REFERENCES companies(id)
    );""")

    # vytvoř výchozího admina
    cur.execute("SELECT COUNT(*) AS c FROM users")
    if cur.fetchone()["c"] == 0:
        username = ADMIN_USERNAME
        password = ADMIN_PASSWORD or "admin"
        cur.execute("INSERT INTO users(username,password) VALUES(?,?)",(username,password))
        print(f"[INIT] Vytvořen admin: {username} / {password} (změňte v /admin/profil)")

    con.commit()
    con.close()

def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or str(uuid.uuid4())[:8]

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapper

def save_file(file_storage, dst_folder: Path) -> str:
    ext = file_storage.filename.rsplit(".",1)[-1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError("Nepodporovaný typ souboru")
    dst_folder.mkdir(parents=True, exist_ok=True)
    filename = f"source.{ext}"
    file_storage.save(dst_folder / filename)
    return filename

def make_qr_png(url: str, out_path: Path):
    img = qrcode.make(url)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)

# ==================== Šablony (Jinja2) ====================
LAYOUT = r"""
<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <meta name="apple-mobile-web-app-capable" content="yes"/>
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"/>
  <title>{{ title or 'Akreditace' }}</title>
  <style>
    :root{--green:#16a34a;--red:#dc2626;--bg:#0b0e11;--card:#111827;--text:#e5e7eb;--muted:#9ca3af}
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,sans-serif}
    .container{max-width:980px;margin:32px auto;padding:0 16px}
    .card{background:var(--card);border-radius:16px;padding:20px;box-shadow:0 6px 30px rgba(0,0,0,.25)}
    .btn{display:inline-block;padding:10px 14px;border-radius:12px;background:#334155;color:#e2e8f0;border:1px solid #475569;cursor:pointer}
    .btn:hover{filter:brightness(1.1)}
    .btn-danger{background:#7f1d1d;border-color:#991b1b}
    .btn-green{background:#065f46;border-color:#047857}
    .input,select{width:100%;padding:10px 12px;border-radius:10px;border:1px solid #334155;background:#0f172a;color:#e5e7eb}
    .table{width:100%;border-collapse:collapse}
    .table th,.table td{padding:10px;border-bottom:1px solid #1f2937;text-align:left}
    .banner{padding:14px 16px;text-align:center;font-size:20px;font-weight:800;letter-spacing:.5px}
    .ok{background:var(--green);color:#fff}
    .bad{background:var(--red);color:#fff}
    .thumb{border-radius:12px;background:#0b1220;padding:8px;border:1px solid #19243b;max-width:100%;height:auto}
    .qr{max-width:220px}
    .muted{color:var(--muted)}
    .topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
    .logo{font-weight:900;letter-spacing:.5px}
    .pad{padding:8px 0}
  </style>
  <script>
    function startClock(){
      const els=document.querySelectorAll('[data-clock]');
      const z=n=>n<10?('0'+n):n;
      function tick(){
        const d=new Date();
        const s=`${z(d.getDate())}.${z(d.getMonth()+1)}.${d.getFullYear()} ${z(d.getHours())}:${z(d.getMinutes())}:${z(d.getSeconds())}`;
        els.forEach(e=>e.textContent=s);
      }
      tick(); setInterval(tick,1000);
    }
    document.addEventListener('DOMContentLoaded', startClock);
  </script>
</head>
<body><div class="container">{% block body %}{% endblock %}</div></body>
</html>
"""

PUBLIC_PAGE = r"""
{% extends "layout" %}
{% block body %}
  <div class="card">
    <div class="banner {{ 'ok' if acc['active'] else 'bad' }}">
      {{ 'AKTIVNÍ AKREDITACE' if acc['active'] else 'NEAKTIVNÍ AKREDITACE' }} — <span data-clock></span>
    </div>
    <div class="pad"></div>
    {% if acc['filename'].lower().endswith('.pdf') %}
      <object data="{{ file_url }}" type="application/pdf" width="100%" height="800px">
        <iframe src="{{ file_url }}" width="100%" height="800px"></iframe>
        <p>Nelze vložit PDF. <a href="{{ file_url }}" target="_blank">Otevřít PDF</a></p>
      </object>
    {% else %}
      <img class="thumb" src="{{ file_url }}" alt="Akreditace">
    {% endif %}
    <div class="pad"></div>
    <div class="banner {{ 'ok' if acc['active'] else 'bad' }}">
      {{ 'AKTIVNÍ AKREDITACE' if acc['active'] else 'NEAKTIVNÍ AKREDITACE' }} — <span data-clock></span>
    </div>
    <div class="pad"><span class="muted">Firma: {{ company['name'] }}</span></div>
  </div>
{% endblock %}
"""

LOGIN_PAGE = r"""
{% extends "layout" %}
{% block body %}
  <div class="card" style="max-width:520px;margin:0 auto;">
    <h2 class="logo">Přihlášení</h2>
    <form method="post">
      <label>Uživatelské jméno</label>
      <input class="input" name="username" required />
      <div style="height:8px"></div>
      <label>Heslo</label>
      <input type="password" class="input" name="password" required />
      <div style="height:16px"></div>
      <button class="btn btn-green">Přihlásit</button>
    </form>
    {% if error %}<p class="muted">{{ error }}</p>{% endif %}
  </div>
{% endblock %}
"""

ADMIN_HOME = r"""
{% extends "layout" %}
{% block body %}
  <div class="topbar">
    <div class="logo">Administrace</div>
    <div>Přihlášen: <strong>{{ user }}</strong> — <a href="{{ url_for('admin_logout') }}">Odhlásit</a></div>
  </div>
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <h2>Firmy</h2>
      <a class="btn" href="{{ url_for('admin_new_company') }}">+ Nová firma</a>
    </div>
    <table class="table">
      <tr><th>Název</th><th>Slug</th><th>Akreditace</th><th></th></tr>
      {% for c in companies %}
        <tr>
          <td>{{ c['name'] }}</td>
          <td class="muted">{{ c['slug'] }}</td>
          <td>{{ c['count'] }}</td>
          <td><a class="btn" href="{{ url_for('admin_company', slug=c['slug']) }}">Otevřít</a></td>
        </tr>
      {% endfor %}
    </table>
  </div>
{% endblock %}
"""

COMPANY_PAGE = r"""
{% extends "layout" %}
{% block body %}
  <div class="topbar">
    <div class="logo"><a href="{{ url_for('admin_home') }}">← Zpět</a> / Firma: <strong>{{ company['name'] }}</strong></div>
    <div>Přihlášen: <strong>{{ user }}</strong> — <a href="{{ url_for('admin_logout') }}">Odhlásit</a></div>
  </div>

  <div class="card">
    <h3>Nová akreditace</h3>
    <form method="post" enctype="multipart/form-data" action="{{ url_for('admin_add_accreditation', slug=company['slug']) }}">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div>
          <label>Název / popis</label>
          <input class="input" name="title" placeholder="např. Jan Novák – Crew" required />
        </div>
        <div>
          <label>Soubor (PNG, JPG, WEBP, PDF)</label>
          <input class="input" type="file" name="file" accept="image/*,.pdf" required />
        </div>
      </div>
      <div style="height:10px"></div>
      <button class="btn btn-green" type="submit">Přidat</button>
    </form>
  </div>

  <div class="card">
    <h3>Akreditace</h3>
    <table class="table">
      <tr><th>Stav</th><th>Název</th><th>QR</th><th>Soubor</th><th>Vytvořeno</th><th>Akce</th></tr>
      {% for a in accs %}
        <tr>
          <td>{% if a['active'] %}<span class="ok" style="padding:4px 8px;border-radius:10px;">AKTIVNÍ</span>{% else %}<span class="bad" style="padding:4px 8px;border-radius:10px;">NEAKTIVNÍ</span>{% endif %}</td>
          <td>{{ a['title'] }}</td>
          <td>
            <img class="qr" src="{{ url_for('qr_image', acc_uuid=a['uuid']) }}" alt="QR">
            <div><a href="{{ public_url(a['uuid']) }}" target="_blank">Veřejná stránka</a></div>
          </td>
          <td><a href="{{ file_url(a) }}" target="_blank">Soubor</a></td>
          <td class="muted">{{ a['created_at'] }}</td>
          <td style="display:flex;gap:8px;">
            <form method="post" action="{{ url_for('admin_toggle_accreditation', slug=company['slug'], acc_uuid=a['uuid']) }}">
              <button class="btn" title="Přepnout stav">Přepnout</button>
            </form>
            <form method="post" action="{{ url_for('admin_delete_accreditation', slug=company['slug'], acc_uuid=a['uuid']) }}" onsubmit="return confirm('Opravdu smazat?');">
              <button class="btn btn-danger" title="Smazat">Smazat</button>
            </form>
          </td>
        </tr>
      {% endfor %}
    </table>
  </div>
{% endblock %}
"""

NEW_COMPANY = r"""
{% extends "layout" %}
{% block body %}
  <div class="topbar">
    <div class="logo"><a href="{{ url_for('admin_home') }}">← Zpět</a></div>
    <div>Přihlášen: <strong>{{ user }}</strong> — <a href="{{ url_for('admin_logout') }}">Odhlásit</a></div>
  </div>
  <div class="card" style="max-width:640px">
    <h3>Nová firma</h3>
    <form method="post">
      <label>Název firmy</label>
      <input class="input" name="name" placeholder="např. Festival XYZ s.r.o." required />
      <div style="height:8px"></div>
      <label>Slug (URL identifikátor) — nech prázdné, vygeneruje se automaticky</label>
      <input class="input" name="slug" placeholder="např. festival-xyz" />
      <div style="height:12px"></div>
      <button class="btn btn-green">Vytvořit</button>
    </form>
  </div>
{% endblock %}
"""

PROFILE_PAGE = r"""
{% extends "layout" %}
{% block body %}
  <div class="topbar">
    <div class="logo"><a href="{{ url_for('admin_home') }}">← Zpět</a></div>
    <div>Přihlášen: <strong>{{ user }}</strong> — <a href="{{ url_for('admin_logout') }}">Odhlásit</a></div>
  </div>
  <div class="card" style="max-width:640px;">
    <h3>Změna hesla</h3>
    <form method="post">
      <label>Nové heslo</label>
      <input class="input" type="password" name="password" required />
      <div style="height:12px"></div>
      <button class="btn btn-green">Uložit</button>
    </form>
  </div>
{% endblock %}
"""

# Registrace šablon (musí být po definici šablon)
app.jinja_loader = DictLoader({
    "layout": LAYOUT,
    "public_page.html": PUBLIC_PAGE,
    "login.html": LOGIN_PAGE,
    "admin_home.html": ADMIN_HOME,
    "company_page.html": COMPANY_PAGE,
    "new_company.html": NEW_COMPANY,
    "profile.html": PROFILE_PAGE
})

# Pomocník do šablon – absolutní veřejná URL
BASE_URL = os.environ.get("BASE_URL")

def build_public_url(u):
    if BASE_URL:
        return f"{BASE_URL}/a/{u}"
    return url_for("public_accreditation", acc_uuid=u, _external=True)

app.jinja_env.globals.update(public_url=build_public_url)

# ==================== Routu – veřejné ====================
@app.route("/")
def index():
    return redirect(url_for("admin_login"))

@app.route("/a/<acc_uuid>")
def public_accreditation(acc_uuid):
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM accreditations WHERE uuid=?", (acc_uuid,))
    acc = cur.fetchone()
    if not acc:
        con.close()
        abort(404)
    cur.execute("SELECT * FROM companies WHERE id=?", (acc["company_id"],))
    company = cur.fetchone()
    con.close()

    file_path = UPLOAD_DIR / company["slug"] / acc_uuid / acc["filename"]
    if not file_path.exists():
        abort(404)

    return render_template_string(
        PUBLIC_PAGE,
        acc=acc,
        company=company,
        file_url=url_for("uploaded_file", company_slug=company["slug"], acc_uuid=acc_uuid, filename=acc["filename"])
    )

@app.route("/uploads/<company_slug>/<acc_uuid>/<path:filename>")
def uploaded_file(company_slug, acc_uuid, filename):
    folder = UPLOAD_DIR / company_slug / acc_uuid
    return send_from_directory(folder, filename, as_attachment=False)

@app.route("/qr/<acc_uuid>.png")
def qr_image(acc_uuid):
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT a.uuid, c.slug
        FROM accreditations a JOIN companies c ON a.company_id=c.id
        WHERE a.uuid=?
    """, (acc_uuid,))
    row = cur.fetchone()
    con.close()
    if not row:
        abort(404)
    qr_path = UPLOAD_DIR / row["slug"] / acc_uuid / "qr.png"
    if not qr_path.exists():
        make_qr_png(url_for("public_accreditation", acc_uuid=acc_uuid, _external=True), qr_path)
    return send_from_directory(qr_path.parent, qr_path.name, as_attachment=False)

# ==================== Routu – admin ====================
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE username=? AND password=?", (username,password))
        user = cur.fetchone()
        con.close()
        if user:
            session["user"] = username
            return redirect(request.args.get("next") or url_for("admin_home"))
        return render_template_string(LOGIN_PAGE, error="Nesprávné přihlašovací údaje")
    return render_template_string(LOGIN_PAGE, error=None)

@app.route("/admin/logout")
@login_required
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.route("/admin")
@login_required
def admin_home():
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT c.*, (SELECT COUNT(*) FROM accreditations a WHERE a.company_id=c.id) AS count FROM companies c ORDER BY name")
    companies = cur.fetchall()
    con.close()
    return render_template_string(ADMIN_HOME, companies=companies, user=session.get("user"))

@app.route("/admin/profil", methods=["GET","POST"])
@login_required
def admin_profile():
    if request.method == "POST":
        pwd = request.form.get("password","")
        if pwd:
            con = get_db()
            cur = con.cursor()
            cur.execute("UPDATE users SET password=? WHERE username=?", (pwd, session.get("user")))
            con.commit()
            con.close()
            flash("Heslo změněno","ok")
            return redirect(url_for("admin_home"))
    return render_template_string(PROFILE_PAGE, user=session.get("user"))

@app.route("/admin/company/new", methods=["GET","POST"])
@login_required
def admin_new_company():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        slug = (request.form.get("slug","") or slugify(name)).strip()
        if not name:
            flash("Vyplňte název firmy","error")
            return render_template_string(NEW_COMPANY, user=session.get("user"))
        con = get_db()
        cur = con.cursor()
        try:
            cur.execute("INSERT INTO companies(name,slug) VALUES(?,?)",(name,slug))
            con.commit()
            (UPLOAD_DIR / slug).mkdir(parents=True, exist_ok=True)
            return redirect(url_for("admin_company", slug=slug))
        except sqlite3.IntegrityError:
            flash("Firma se stejným názvem/slugem již existuje","error")
        finally:
            con.close()
    return render_template_string(NEW_COMPANY, user=session.get("user"))

@app.route("/admin/company/<slug>")
@login_required
def admin_company(slug):
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM companies WHERE slug=?", (slug,))
    company = cur.fetchone()
    if not company:
        con.close()
        abort(404)
    cur.execute("SELECT * FROM accreditations WHERE company_id=? ORDER BY created_at DESC", (company["id"],))
    accs = cur.fetchall()
    con.close()

    def _file_url(a):
        return url_for("uploaded_file", company_slug=slug, acc_uuid=a["uuid"], filename=a["filename"])

    return render_template_string(COMPANY_PAGE, company=company, accs=accs, user=session.get("user"), file_url=_file_url)

@app.route("/admin/company/<slug>/add", methods=["POST"])
@login_required
def admin_add_accreditation(slug):
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM companies WHERE slug=?", (slug,))
    company = cur.fetchone()
    if not company:
        con.close()
        abort(404)

    title = request.form.get("title","").strip()
    file  = request.files.get("file")
    if not title or not file:
        flash("Vyplňte titul a soubor","error")
        return redirect(url_for("admin_company", slug=slug))

    acc_uuid = str(uuid.uuid4())
    folder   = UPLOAD_DIR / slug / acc_uuid
    try:
        filename = save_file(file, folder)
    except ValueError as e:
        flash(str(e),"error")
        return redirect(url_for("admin_company", slug=slug))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""INSERT INTO accreditations(uuid,company_id,title,filename,active,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (acc_uuid, company["id"], title, filename, 1, now))
    con.commit()

    make_qr_png(url_for("public_accreditation", acc_uuid=acc_uuid, _external=True), folder / "qr.png")

    con.close()
    return redirect(url_for("admin_company", slug=slug))

@app.route("/admin/company/<slug>/<acc_uuid>/toggle", methods=["POST"])
@login_required
def admin_toggle_accreditation(slug, acc_uuid):
    con = get_db()
    cur = con.cursor()
    cur.execute("""SELECT a.*, c.slug FROM accreditations a
                   JOIN companies c ON a.company_id=c.id
                   WHERE a.uuid=? AND c.slug=?""", (acc_uuid, slug))
    acc = cur.fetchone()
    if not acc:
        con.close()
        abort(404)
    new_val = 0 if acc["active"] else 1
    cur.execute("UPDATE accreditations SET active=? WHERE id=?", (new_val, acc["id"]))
    con.commit()
    con.close()
    return redirect(url_for("admin_company", slug=slug))

@app.route("/admin/company/<slug>/<acc_uuid>/delete", methods=["POST"])
@login_required
def admin_delete_accreditation(slug, acc_uuid):
    con = get_db()
    cur = con.cursor()
    cur.execute("""SELECT a.*, c.slug FROM accreditations a
                   JOIN companies c ON a.company_id=c.id
                   WHERE a.uuid=? AND c.slug=?""", (acc_uuid, slug))
    acc = cur.fetchone()
    if not acc:
        con.close()
        abort(404)
    cur.execute("DELETE FROM accreditations WHERE id=?", (acc["id"],))
    con.commit()
    con.close()

    folder = UPLOAD_DIR / slug / acc_uuid
    try:
        for p in folder.glob("*"):
            p.unlink(missing_ok=True)
        folder.rmdir()
    except Exception:
        pass

    return redirect(url_for("admin_company", slug=slug))

# ==================== Main ====================
if __name__ == "__main__":
    ensure_dirs()
    init_db()
    # host=0.0.0.0 → přístup i z iPhonu ve stejné Wi-Fi; port 5001 (dle tvé žádosti)
    app.run(debug=True, host="0.0.0.0", port=5001)

