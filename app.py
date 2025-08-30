# app.py
import os
import sqlite3
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "dev"  # ok for local/dev; change for prod

# ---------- SQLite helpers ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sow_database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_schema():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS charger_types (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sows (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                charger_type_id INTEGER,
                content TEXT,
                FOREIGN KEY (charger_type_id) REFERENCES charger_types(id)
            );
        """)
        conn.commit()

# ---------- Pages ----------
@app.get("/")
def index():
    # Home page pulls charger types for the dropdown
    with get_db() as conn:
        chargers = conn.execute(
            "SELECT id, name FROM charger_types ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return render_template("index.html", chargers=chargers)

# Keep endpoint names to match your nav templates
@app.get("/edit_sows", endpoint="edit_sows")
def edit_sows():
    return render_template("edit_sows.html")

# --- Add Charger Types (UI) ---
@app.get("/add_charger_type", endpoint="add_charger_type")
def add_charger_type_get():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name FROM charger_types ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return render_template("add_charger_type.html", charger_types=rows)

@app.post("/add_charger_type")
def add_charger_type_post():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Charger type name cannot be empty.", "error")
        return redirect(url_for("add_charger_type"))
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO charger_types(name) VALUES (?)", (name,))
            conn.commit()
        flash(f"Added charger type: {name}", "success")
    except sqlite3.IntegrityError:
        flash(f"Charger type '{name}' already exists.", "warning")
    return redirect(url_for("add_charger_type"))

# --- Add SOW (UI) ---
# GET: render form WITH charger_types populated
@app.get("/add_sow", endpoint="add_sow")
def add_sow_get():
    with get_db() as conn:
        charger_types = conn.execute(
            "SELECT id, name FROM charger_types ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return render_template("add_sow.html", charger_types=charger_types)

# POST: create the SOW then redirect back to the form
@app.post("/add_sow")
def add_sow_post():
    title = (request.form.get("title") or "").strip()
    charger_type_id = request.form.get("charger_type_id")
    content = (request.form.get("content") or "").strip()

    if not title:
        flash("Title is required.", "error")
        return redirect(url_for("add_sow"))
    if not charger_type_id:
        flash("Please choose a charger type.", "error")
        return redirect(url_for("add_sow"))

    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO sows (title, charger_type_id, content) VALUES (?, ?, ?)",
                (title, charger_type_id, content),
            )
            conn.commit()
        flash("SOW created.", "success")
    except Exception as e:
        flash(f"Error creating SOW: {e}", "error")

    return redirect(url_for("add_sow"))

# ---------- APIs ----------
@app.get("/api/charger_types")
def api_charger_types():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name FROM charger_types ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return jsonify([{"id": r["id"], "name": r["name"]} for r in rows])

@app.get("/api/sows")
def api_sows():
    """
    Returns: [{ "id": int, "title": str }]
    Optional ?charger_type_id= filters results.
    """
    charger_type_id = request.args.get("charger_type_id")
    sql = """
        SELECT id, title
        FROM sows
        WHERE (? IS NULL OR charger_type_id = ?)
        ORDER BY id DESC
    """
    with get_db() as conn:
        rows = conn.execute(sql, (charger_type_id, charger_type_id)).fetchall()
    return jsonify([{"id": r["id"], "title": r["title"]} for r in rows])

# ---------- Dev server ----------
if __name__ == "__main__":
    ensure_schema()
    app.run(host="0.0.0.0", port=5000, debug=True)
