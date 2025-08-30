# app.py
import os
import sqlite3
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, send_file
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
import tempfile
from PIL import Image as PilImage

app = Flask(__name__)
app.secret_key = "dev"

# --- Configuration for file uploads ---
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                check_in_contact TEXT,
                check_in_phone TEXT,
                check_in_instructions TEXT,
                check_out_contact TEXT,
                check_out_phone TEXT,
                check_out_instructions TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sow_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sow_id INTEGER,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                caption TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sow_id) REFERENCES sows (id) ON DELETE CASCADE
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sows (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                name TEXT NOT NULL,
                charger_type_id INTEGER,
                customer_id INTEGER,
                maintenance_scope TEXT,
                parts TEXT,
                tools TEXT,
                documents TEXT,
                service_instructions TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (charger_type_id) REFERENCES charger_types(id),
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );
        """)
        conn.commit()

# ---------- Pages ----------
@app.get("/")
def index():
    with get_db() as conn:
        chargers = conn.execute(
            "SELECT id, name FROM charger_types ORDER BY name COLLATE NOCASE"
        ).fetchall()
        customers = conn.execute(
            "SELECT id, name FROM customers ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return render_template("index.html", charger_types=chargers, customers=customers)

@app.get("/edit_sows", endpoint="edit_sows")
def edit_sows():
    with get_db() as conn:
        sows = conn.execute("""
            SELECT s.*, ct.name as charger_type_name, c.name as customer_name
            FROM sows s
            JOIN charger_types ct ON s.charger_type_id = ct.id
            LEFT JOIN customers c ON s.customer_id = c.id
            ORDER BY s.created_at DESC
        """).fetchall()
    return render_template("edit_sows.html", sows=sows)

@app.get("/edit_sow/<int:sow_id>", endpoint="edit_sow")
def edit_sow_get(sow_id):
    with get_db() as conn:
        sow = conn.execute("SELECT * FROM sows WHERE id = ?", (sow_id,)).fetchone()
        charger_types = conn.execute("SELECT * FROM charger_types ORDER BY name").fetchall()
        customers = conn.execute("SELECT * FROM customers ORDER BY name").fetchall()
        images = conn.execute("SELECT * FROM sow_images WHERE sow_id = ? ORDER BY uploaded_at", (sow_id,)).fetchall()
    if not sow:
        flash("SOW not found!", "error")
        return redirect(url_for("edit_sows"))
    return render_template("edit_sow.html", sow=sow, charger_types=charger_types, customers=customers, images=images)

@app.post("/edit_sow/<int:sow_id>")
def edit_sow_post(sow_id):
    title = request.form.get("title")
    charger_type_id = request.form.get("charger_type_id")
    customer_id = request.form.get("customer_id") or None
    maintenance_scope = request.form.get("maintenance_scope")
    parts = request.form.get("parts")
    tools = request.form.get("tools")
    documents = request.form.get("documents")
    service_instructions = request.form.get("service_instructions")
    
    uploaded_files = request.files.getlist('sow_images')
    new_image_captions = request.form.getlist('new_image_captions')

    try:
        with get_db() as conn:
            conn.execute(
                """
                UPDATE sows SET 
                    title = ?, 
                    name = ?,
                    charger_type_id = ?, 
                    customer_id = ?,
                    maintenance_scope = ?, 
                    parts = ?, 
                    tools = ?, 
                    documents = ?, 
                    service_instructions = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (title, title, charger_type_id, customer_id, maintenance_scope, parts, tools, documents, service_instructions, sow_id)
            )

            # Handle existing image caption updates
            existing_image_ids = request.form.getlist('existing_image_id')
            existing_image_captions = request.form.getlist('existing_caption')
            for img_id, caption in zip(existing_image_ids, existing_image_captions):
                conn.execute('UPDATE sow_images SET caption = ? WHERE id = ?', (caption, img_id))

            # Handle new image uploads with captions
            for i, file in enumerate(uploaded_files):
                if file and file.filename and allowed_file(file.filename):
                    filename = f"{uuid.uuid4()}.{file.filename.rsplit('.', 1)[1].lower()}"
                    original_name = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    caption = new_image_captions[i] if i < len(new_image_captions) else ''
                    conn.execute('''
                        INSERT INTO sow_images (sow_id, filename, original_name, caption)
                        VALUES (?, ?, ?, ?)
                    ''', (sow_id, filename, original_name, caption))

            conn.commit()
        flash("SOW updated successfully!", "success")
    except Exception as e:
        flash(f"An error occurred: {e}", "error")

    return redirect(url_for("edit_sow", sow_id=sow_id))
    
@app.post('/delete_image/<int:sow_id>/<filename>')
def delete_image(sow_id, filename):
    try:
        with get_db() as conn:
            conn.execute('DELETE FROM sow_images WHERE sow_id = ? AND filename = ?', (sow_id, filename))
            conn.commit()
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        return jsonify(success=True)
    except sqlite3.Error as e:
        return jsonify(success=False, error=str(e))

@app.post("/delete_sow/<int:sow_id>", endpoint="delete_sow")
def delete_sow(sow_id):
    try:
        with get_db() as conn:
            # Delete images from the filesystem first
            images = conn.execute('SELECT filename FROM sow_images WHERE sow_id = ?', (sow_id,)).fetchall()
            for img in images:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], img['filename'])
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            # Now delete the SOW and all associated images from the database
            conn.execute("DELETE FROM sows WHERE id = ?", (sow_id,))
            conn.commit()
        flash("SOW deleted successfully!", "success")
    except Exception as e:
        flash(f"An error occurred: {e}", "error")
    return redirect(url_for("edit_sows"))

@app.get("/add_customer", endpoint="add_customer")
def add_customer_get():
    return render_template("add_customer.html")

@app.post("/add_customer")
def add_customer_post():
    name = (request.form.get("name") or "").strip()
    check_in_contact = (request.form.get("check_in_contact") or "").strip()
    check_in_phone = (request.form.get("check_in_phone") or "").strip()
    check_in_instructions = (request.form.get("check_in_instructions") or "").strip()
    check_out_contact = (request.form.get("check_out_contact") or "").strip()
    check_out_phone = (request.form.get("check_out_phone") or "").strip()
    check_out_instructions = (request.form.get("check_out_instructions") or "").strip()

    if not name:
        flash("Customer name is required.", "error")
        return redirect(url_for("add_customer"))

    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO customers (name, check_in_contact, check_in_phone, check_in_instructions, check_out_contact, check_out_phone, check_out_instructions)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, check_in_contact, check_in_phone, check_in_instructions, check_out_contact, check_out_phone, check_out_instructions),
            )
            conn.commit()
        flash(f"Customer '{name}' added successfully.", "success")
    except sqlite3.IntegrityError:
        flash(f"Customer '{name}' already exists.", "warning")
    except Exception as e:
        flash(f"Error creating customer: {e}", "error")

    return redirect(url_for("settings"))

@app.get("/edit_customer/<int:customer_id>", endpoint="edit_customer")
def edit_customer_get(customer_id):
    with get_db() as conn:
        customer = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        flash("Customer not found.", "error")
        return redirect(url_for("settings"))
    return render_template("edit_customer.html", customer=customer)

@app.post("/edit_customer/<int:customer_id>")
def edit_customer_post(customer_id):
    name = (request.form.get("name") or "").strip()
    check_in_contact = (request.form.get("check_in_contact") or "").strip()
    check_in_phone = (request.form.get("check_in_phone") or "").strip()
    check_in_instructions = (request.form.get("check_in_instructions") or "").strip()
    check_out_contact = (request.form.get("check_out_contact") or "").strip()
    check_out_phone = (request.form.get("check_out_phone") or "").strip()
    check_out_instructions = (request.form.get("check_out_instructions") or "").strip()
    
    if not name:
        flash("Customer name is required.", "error")
        return redirect(url_for("edit_customer", customer_id=customer_id))
    
    try:
        with get_db() as conn:
            conn.execute(
                """
                UPDATE customers SET
                    name = ?,
                    check_in_contact = ?,
                    check_in_phone = ?,
                    check_in_instructions = ?,
                    check_out_contact = ?,
                    check_out_phone = ?,
                    check_out_instructions = ?
                WHERE id = ?
                """,
                (name, check_in_contact, check_in_phone, check_in_instructions, check_out_contact, check_out_phone, check_out_instructions, customer_id),
            )
            conn.commit()
        flash(f"Customer '{name}' updated successfully.", "success")
    except sqlite3.IntegrityError:
        flash(f"Customer '{name}' already exists.", "warning")
    except Exception as e:
        flash(f"Error updating customer: {e}", "error")

    return redirect(url_for("settings"))

@app.post("/delete_customer/<int:customer_id>")
def delete_customer(customer_id):
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
            conn.commit()
        flash("Customer deleted successfully.", "success")
    except Exception as e:
        flash(f"An error occurred: {e}", "error")
    return redirect(url_for("settings"))

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

@app.post("/delete_charger_type/<int:type_id>")
def delete_charger_type(type_id):
    with get_db() as conn:
        sow_count = conn.execute(
            "SELECT COUNT(*) FROM sows WHERE charger_type_id = ?", (type_id,)
        ).fetchone()[0]
        if sow_count > 0:
            flash("Cannot delete charger type with associated SOWs.", "error")
        else:
            conn.execute("DELETE FROM charger_types WHERE id = ?", (type_id,))
            conn.commit()
            flash("Charger type deleted successfully.", "success")
    return redirect(url_for("add_charger_type"))

# --- Add SOW (UI) ---
@app.get("/add_sow", endpoint="add_sow")
def add_sow_get():
    with get_db() as conn:
        charger_types = conn.execute(
            "SELECT id, name FROM charger_types ORDER BY name COLLATE NOCASE"
        ).fetchall()
        customers = conn.execute(
            "SELECT id, name FROM customers ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return render_template("add_sow.html", charger_types=charger_types, customers=customers)

@app.post("/add_sow")
def add_sow_post():
    title = (request.form.get("title") or "").strip()
    charger_type_id = request.form.get("charger_type_id")
    customer_id = request.form.get("customer_id") or None
    maintenance_scope = (request.form.get("maintenance_scope") or "").strip()
    parts = (request.form.get("parts") or "").strip()
    tools = (request.form.get("tools") or "").strip()
    documents = (request.form.get("documents") or "").strip()
    service_instructions = (request.form.get("service_instructions") or "").strip()
    uploaded_files = request.files.getlist('sow_images')
    new_image_captions = request.form.getlist('new_image_captions')
    
    if not title or not charger_type_id:
        flash("Title and Charger Type are required.", "error")
        return redirect(url_for("add_sow"))

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sows (title, name, charger_type_id, customer_id, maintenance_scope, parts, tools, documents, service_instructions) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title, title, charger_type_id, customer_id, maintenance_scope, parts, tools, documents, service_instructions),
            )
            sow_id = cursor.lastrowid

            for i, file in enumerate(uploaded_files):
                if file and allowed_file(file.filename):
                    filename = f"{uuid.uuid4()}.{file.filename.rsplit('.', 1)[1].lower()}"
                    original_name = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    caption = new_image_captions[i] if i < len(new_image_captions) else ''
                    cursor.execute('''
                        INSERT INTO sow_images (sow_id, filename, original_name, caption)
                        VALUES (?, ?, ?, ?)
                    ''', (sow_id, filename, original_name, caption))
            conn.commit()
        flash("SOW created.", "success")
    except Exception as e:
        flash(f"Error creating SOW: {e}", "error")

    return redirect(url_for("add_sow"))

# ---------- APIs ----------
@app.get("/api/sows")
def api_sows():
    charger_type_id = request.args.get("charger_type_id")
    customer_id = request.args.get("customer_id")
    sql = """
        SELECT id, title
        FROM sows
        WHERE (? IS NULL OR charger_type_id = ?) AND (? IS NULL OR customer_id = ?)
        ORDER BY id DESC
    """
    with get_db() as conn:
        rows = conn.execute(sql, (charger_type_id, charger_type_id, customer_id, customer_id)).fetchall()
    return jsonify([{"id": r["id"], "title": r["title"]} for r in rows])

@app.get("/api/sows/<int:sow_id>")
def api_get_sow(sow_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sows WHERE id = ?", (sow_id,)).fetchone()
    if not row:
        return jsonify({"error": "SOW not found"}), 404
    return jsonify(dict(row))

@app.get("/api/sow_images/<int:sow_id>")
def api_sow_images(sow_id):
    with get_db() as conn:
        images = conn.execute("SELECT * FROM sow_images WHERE sow_id = ?", (sow_id,)).fetchall()
    return jsonify([dict(i) for i in images])

@app.get("/api/customers")
def api_customers():
    with get_db() as conn:
        rows = conn.execute("SELECT id, name FROM customers ORDER BY name COLLATE NOCASE").fetchall()
    return jsonify([{"id": r["id"], "name": r["name"]} for r in rows])

@app.get("/api/customers/<int:customer_id>")
def api_get_customer(customer_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not row:
        return jsonify({"error": "Customer not found"}), 404
    return jsonify(dict(row))

@app.route('/generate_pdf/<int:sow_id>')
@app.route('/generate_pdf/<int:sow_id>/<int:customer_id>')
def generate_pdf(sow_id, customer_id=None):
    try:
        with sqlite3.connect('sow_database.db') as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM sows WHERE id = ?', (sow_id,))
            sow_data = cursor.fetchone()
            if not sow_data:
                flash('SOW not found!', 'error')
                return redirect(url_for('index'))

            customer_data = None
            if customer_id:
                cursor.execute('SELECT * FROM customers WHERE id = ?', (customer_id,))
                customer_data = cursor.fetchone()
            
            cursor.execute('SELECT * FROM sow_images WHERE sow_id = ? ORDER BY uploaded_at', (sow_id,))
            image_data = cursor.fetchall()

            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            doc = SimpleDocTemplate(temp_file.name, pagesize=letter)
            styles = getSampleStyleSheet()

            styles.add(ParagraphStyle(name='TitleStyle', fontSize=24, spaceAfter=12, alignment=TA_CENTER, fontName='Helvetica-Bold'))
            styles.add(ParagraphStyle(name='HeadingStyle', fontSize=14, spaceAfter=6, fontName='Helvetica-Bold', leading=18))
            styles.add(ParagraphStyle(name='NormalStyle', fontSize=12, spaceAfter=12, leading=14))
            styles.add(ParagraphStyle(name='CaptionStyle', fontSize=10, textColor=colors.grey, spaceBefore=4, spaceAfter=12, alignment=TA_CENTER))

            story = []

            now = datetime.now().strftime("%a %b %d %H:%M:%S %Y CDT")
            story.append(Paragraph(f"SOW Created [{now}]", styles['NormalStyle']))
            story.append(Paragraph("TECH SUPPORT CONTACT INFORMATION", styles['HeadingStyle']))
            story.append(Paragraph("BTC Power Technical Support Hotline 1-855-901-1558", styles['NormalStyle']))
            story.append(Spacer(1, 0.25 * inch))

            if sow_data['title']:
                story.append(Paragraph(sow_data['title'], styles['TitleStyle']))
                story.append(Spacer(1, 0.25 * inch))

            if customer_data:
                story.append(PageBreak())
                story.append(Paragraph('CUSTOMER CHECK-IN/CHECK-OUT INFORMATION', styles['HeadingStyle']))
                
                check_in_fields = [
                    ('Check-in Contact:', 'check_in_contact'),
                    ('Check-in Phone:', 'check_in_phone'),
                    ('Check-in Instructions:', 'check_in_instructions')
                ]
                
                for label, field in check_in_fields:
                    if customer_data[field]:
                        story.append(Paragraph(f'<b>{label}</b> {customer_data[field]}', styles['NormalStyle']))
                
                story.append(Spacer(1, 0.2 * inch))
                
                check_out_fields = [
                    ('Check-out Contact:', 'check_out_contact'),
                    ('Check-out Phone:', 'check_out_phone'),
                    ('Check-out Instructions:', 'check_out_instructions')
                ]
                
                for label, field in check_out_fields:
                    if customer_data[field]:
                        story.append(Paragraph(f'<b>{label}</b> {customer_data[field]}', styles['NormalStyle']))

            fields = [
                ('MAINTENANCE SCOPE', 'maintenance_scope'),
                ('PARTS', 'parts'),
                ('TOOLS', 'tools'),
                ('DOCUMENTS', 'documents'),
                ('SERVICE INSTRUCTIONS', 'service_instructions')
            ]

            for heading, field in fields:
                if sow_data[field]:
                    story.append(Paragraph(heading, styles['HeadingStyle']))
                    story.append(Paragraph(sow_data[field], styles['NormalStyle']))
                    story.append(Spacer(1, 0.2 * inch))

            if image_data:
                story.append(PageBreak())
                story.append(Paragraph('REFERENCE IMAGES', styles['HeadingStyle']))
                story.append(Spacer(1, 0.2 * inch))
                for img in image_data:
                    image_path = os.path.join(app.config['UPLOAD_FOLDER'], img['filename'])
                    if os.path.exists(image_path):
                        if img['filename'].lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                            try:
                                pil_img = PilImage.open(image_path)
                                img_width, img_height = pil_img.size
                                max_width = letter[0] - 2 * inch
                                max_height = letter[1] - 2 * inch
                                
                                ratio = min(max_width / img_width, max_height / img_height)
                                
                                rl_img = RLImage(image_path, width=img_width * ratio, height=img_height * ratio)
                                story.append(rl_img)
                                
                                if img['caption']:
                                    story.append(Paragraph(img['caption'], styles['CaptionStyle']))
                                else:
                                    story.append(Paragraph(img['original_name'], styles['CaptionStyle']))
                                story.append(Spacer(1, 0.2 * inch))
                            except Exception as e:
                                story.append(Paragraph(f'<i>Error displaying image: {img["original_name"]}</i>', styles['NormalStyle']))
                                story.append(Spacer(1, 0.2 * inch))
                        elif img['filename'].lower().endswith('.pdf'):
                            story.append(Paragraph(f'<b>Reference Document:</b> {img["original_name"]}', styles['NormalStyle']))
                            story.append(Paragraph(f'<i>{img["caption"]}</i>' if img['caption'] else '', styles['CaptionStyle']))
                            story.append(Spacer(1, 0.2 * inch))

            doc.build(story)
            temp_file.seek(0)
            return send_file(temp_file.name, as_attachment=True, download_name=f'SOW-{sow_data["title"]}.pdf')

    except Exception as e:
        flash(f'An error occurred during PDF generation: {str(e)}', 'error')
        return redirect(url_for('index'))

# --- Dev server ---
if __name__ == "__main__":
    ensure_schema()
    app.run(host="0.0.0.0", port=5000, debug=True)
