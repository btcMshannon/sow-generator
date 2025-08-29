from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
import sqlite3
from datetime import datetime
import os
import uuid
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
import tempfile

app = Flask(__name__, template_folder='templates')
app.secret_key = 'your-secret-key-here'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    with sqlite3.connect('sow_database.db') as conn:
        conn.execute('PRAGMA journal_mode=WAL;')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS charger_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
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
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sow_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sow_id INTEGER,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                caption TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sow_id) REFERENCES sows (id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                charger_type_id INTEGER,
                customer_id INTEGER,
                name TEXT NOT NULL,
                title TEXT,
                maintenance_scope TEXT,
                parts TEXT,
                tools TEXT,
                documents TEXT,
                service_instructions TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (charger_type_id) REFERENCES charger_types (id),
                FOREIGN KEY (customer_id) REFERENCES customers (id)
            )
        ''')

init_db()

@app.route('/')
def index():
    with sqlite3.connect('sow_database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM charger_types ORDER BY name')
        charger_types = cursor.fetchall()
        cursor.execute('SELECT * FROM customers ORDER BY name')
        customers = cursor.fetchall()
    return render_template('index.html', charger_types=charger_types, customers=customers)

@app.route('/get_sows')
def get_sows():
    with sqlite3.connect('sow_database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, ct.name as charger_type_name, c.name as customer_name
            FROM sows s
            LEFT JOIN charger_types ct ON s.charger_type_id = ct.id
            LEFT JOIN customers c ON s.customer_id = c.id
            ORDER BY s.created_at DESC
        ''')
        sows = cursor.fetchall()
    return render_template('get_sows.html', sows=sows)

@app.route('/add_sow', methods=['GET', 'POST'])
def add_sow():
    if request.method == 'POST':
        try:
            charger_type_id = request.form.get('charger_type_id')
            customer_id = request.form.get('customer_id') or None
            name = request.form.get('sow_title')
            title = request.form.get('sow_title')
            maintenance_scope = request.form.get('maintenance_scope')
            parts = request.form.get('parts')
            tools = request.form.get('tools')
            documents = request.form.get('documents')
            service_instructions = request.form.get('service_instructions')
            uploaded_files = request.files.getlist('sow_images')
            captions = request.form.getlist('captions')

            with sqlite3.connect('sow_database.db') as conn:
                conn.execute('PRAGMA journal_mode=WAL;')
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO sows (charger_type_id, customer_id, name, title, maintenance_scope, parts, tools, documents, service_instructions)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (charger_type_id, customer_id, name, title, maintenance_scope, parts, tools, documents, service_instructions))
                sow_id = cursor.lastrowid

                for i, file in enumerate(uploaded_files):
                    if file and file.filename and allowed_file(file.filename):
                        filename = f"{uuid.uuid4()}.{file.filename.rsplit('.', 1)[1].lower()}"
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(file_path)
                        caption = captions[i] if i < len(captions) else ''
                        cursor.execute('''
                            INSERT INTO sow_images (sow_id, filename, original_name, caption)
                            VALUES (?, ?, ?, ?)
                        ''', (sow_id, filename, file.filename, caption))

                conn.commit()
            flash('SOW created successfully!', 'success')
            return redirect(url_for('get_sows'))

        except sqlite3.OperationalError as e:
            flash(f'Database error: {str(e)}', 'error')
            return redirect(url_for('add_sow'))

    with sqlite3.connect('sow_database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM charger_types ORDER BY name')
        charger_types = cursor.fetchall()
        cursor.execute('SELECT * FROM customers ORDER BY name')
        customers = cursor.fetchall()

    return render_template('add_sow.html', charger_types=charger_types, customers=customers)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
