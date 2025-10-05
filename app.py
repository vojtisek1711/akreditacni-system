import os, sqlite3, uuid as _uuid
from pathlib import Path
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    send_from_directory, session, abort
)

# ========= Nastavení =========
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this")

# Render má zapisovatelné /tmp → používáme pro DB i soubory
DB_PATH   = os.environ.get("DB_PATH",  "/tmp/akreditace.db")
FILES_DIR = os.environ.get("FILES_DIR","/tmp/akreditace_files")
Path(FILES_DIR).mkdir(parents=True, exist_ok=True)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "adminvstup")
BASE_URL       = os.environ.get("BASE_URL", "")  # po deploy doplň svou https://…onrender.com

# ========= DB =========
def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def ensure_db():
    con = get_db(); cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accreditations(
            uuid TEXT PRIMARY KEY,
            company TEXT,
            valid_until TEXT,
            active INTEGER DEFAULT 1,
            filepath TEXT
        )
    """)
    con.commit(); con.close()

# helper pro absolutní veřejnou URL (pro QR i šablony)
def public_url(u):
    return f"{BASE_URL}/a/{u}" if BASE_URL else url_for("public_accreditation", uuid=u, _external=True)

# zpřístupníme do šablon i funkci pro aktuální čas
app.jinja_env.globals.update(
    public_url=public_url,
    now=lambda: datetime.now().strftime("%d.%m.%Y %H:%M:%S")
)

# ========= Veřejné routy =========
@app.route("/")
def home():
    return redirect(url_for("admin_login"))

@app.route("/a/<uuid>")
def public_accreditation(uuid):
    con = get_db(); cur = con.cursor()
    cur.execute("SELECT * FROM accreditations WHERE uuid=?", (uuid,))
    acc = cur.fetchone(); con.close()
    if not acc: abort(404)
    acc = dict(acc)
    acc_file_url = None
    if acc.get("filepath"):
        p = Path(acc["filepath"])
        if p.exists():
            acc_file_url = url_for("files", fname=p.name, _external=False)
    return render_template("public.html", acc=acc, acc_file_url=acc_file_url)

# ========= Admin (simple session) =========
@app.route("/admin", methods=["GET","POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if (request.form.get("username")==ADMIN_USERNAME and
            request.form.get("password")==ADMIN_PASSWORD):
            session["logged_in"] = True
            return redirect(url_for("admin_home"))
        error = "Neplatné přihlašovací údaje"
    return render_template("login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def _w(*a, **kw):
        if not session.get("logged_in"):
            return redirect(url_for("admin_login"))
        return fn(*a, **kw)
    return _w

@app.route("/admin/home")
@login_required
def admin_home():
    con = get_db(); cur = con.cursor()
    cur.execute("SELECT * FROM accreditations ORDER BY ROWID DESC")
    accs = cur.fetchall(); con.close()
    return render_template("admin_home.html", accs=accs)

@app.route("/admin/new", methods=["POST"])
@login_required
def admin_new():
    u = str(_uuid.uuid4())
    con = get_db(); cur = con.cursor()
    cur.execute("INSERT INTO accreditations (uuid, active) VALUES (?,1)", (u,))
    con.commit(); con.close()
    return redirect(url_for("acc_detail", uuid=u))

@app.route("/admin/acc/<uuid>")
@login_required
def acc_detail(uuid):
    con = get_db(); cur = con.cursor()
    cur.execute("SELECT * FROM accreditations WHERE uuid=?", (uuid,))
    acc = cur.fetchone(); con.close()
    if not acc: abort(404)
    return render_template("acc_detail.html", acc=acc)

@app.route("/admin/acc/<uuid>/update", methods=["POST"])
@login_required
def acc_update(uuid):
    company = request.form.get("company") or None
    valid_until = request.form.get("valid_until") or None
    con = get_db(); cur = con.cursor()
    cur.execute("UPDATE accreditations SET company=?, valid_until=? WHERE uuid=?", (company, valid_until, uuid))
    con.commit(); con.close()
    return redirect(url_for("acc_detail", uuid=uuid))

@app.route("/admin/acc/<uuid>/toggle", methods=["POST"])
@login_required
def acc_toggle(uuid):
    con = get_db(); cur = con.cursor()
    cur.execute("SELECT active FROM accreditations WHERE uuid=?", (uuid,))
    row = cur.fetchone()
    if not row: 
        con.close(); abort(404)
    new_state = 0 if row["active"] else 1
    cur.execute("UPDATE accreditations SET active=? WHERE uuid=?", (new_state, uuid))
    con.commit(); con.close()
    return redirect(url_for("admin_home"))

@app.route("/admin/acc/<uuid>/upload", methods=["POST"])
@login_required
def acc_upload(uuid):
    f = request.files.get("file")
    if not f:
        return redirect(url_for("acc_detail", uuid=uuid))
    ext = (f.filename.rsplit(".",1)[-1] or "").lower()
    if ext not in {"png","jpg","jpeg","webp","pdf"}:
        return redirect(url_for("acc_detail", uuid=uuid))
    fname = f"{uuid}.{ext}"
    path = Path(FILES_DIR) / fname
    f.save(path)
    con = get_db(); cur = con.cursor()
    cur.execute("UPDATE accreditations SET filepath=? WHERE uuid=?", (str(path), uuid))
    con.commit(); con.close()
    return redirect(url_for("acc_detail", uuid=uuid))

@app.route("/admin/acc/<uuid>/qr")
@login_required
def acc_qr(uuid):
    import qrcode
    from io import BytesIO
    img = qrcode.make(public_url(uuid))
    bio = BytesIO(); img.save(bio, format="PNG"); bio.seek(0)
    from flask import send_file
    return send_file(bio, mimetype="image/png", download_name=f"qr-{uuid}.png")

# soubory (obrázek/pdf akreditace)
@app.route("/files/<path:fname>")
def files(fname):
    return send_from_directory(FILES_DIR, fname, as_attachment=False)

# ========= spouštěcí část =========
if __name__ == "__main__":
    ensure_db()
    port = int(os.environ.get("PORT", "5001"))  # Render dává PORT
    app.run(host="0.0.0.0", port=port)
