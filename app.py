from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)

# Přístupové údaje z proměnných prostředí
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "adminvstup")
BASE_URL = os.environ.get("BASE_URL", "")

@app.route("/")
def index():
    return redirect(url_for("admin_login"))

@app.route("/a/<uuid>")
def public_accreditation(uuid):
    return render_template("public.html", uuid=uuid)

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form["username"] == ADMIN_USERNAME and request.form["password"] == ADMIN_PASSWORD:
            return redirect(url_for("admin_home"))
        else:
            error = "Neplatné přihlašovací údaje"
    return render_template("login.html", error=error)

@app.route("/admin/home")
def admin_home():
    return "<h1>Admin sekce</h1>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
