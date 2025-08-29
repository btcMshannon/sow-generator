from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
import sqlite3
from datetime import datetime
import os
import uuid
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
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

@app.route('/edit_sow/<int:sow_id>', methods=['GET', 'POST'])
def edit_sow_detail(sow_id):
    if request.method == 'POST':
        try:
            charger_type_id = request.form.get('charger_type_id')
            title = request.form.get('sow_title')
            maintenance_scope = request.form.get('maintenance_scope')
            parts = request.form.get('parts')
            tools = request.form.get('tools')
            documents = request.form.get('documents')
            service_instructions = request.form.get('service_instructions')
            
            # Handle new image uploads
            uploaded_files = request.files.getlist('sow_images')
            new_image_captions = request.form.getlist('new_image_captions')

            with sqlite3.connect('sow_database.db') as conn:
                conn.execute('PRAGMA journal_mode=WAL;')
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE sows SET
                        charger_type_id = ?,
                        title = ?,
                        maintenance_scope = ?,
                        parts = ?,
                        tools = ?,
                        documents = ?,
                        service_instructions = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (charger_type_id, title, maintenance_scope, parts, tools, documents, service_instructions, sow_id))
                
                # Handle existing image caption updates
                existing_image_ids = request.form.getlist('existing_image_id')
                existing_image_captions = request.form.getlist('existing_caption')
                for img_id, caption in zip(existing_image_ids, existing_image_captions):
                    cursor.execute('UPDATE sow_images SET caption = ? WHERE id = ?', (caption, img_id))

                # Handle new image uploads with captions
                for i, file in enumerate(uploaded_files):
                    if file and file.filename and allowed_file(file.filename):
                        filename = f"{uuid.uuid4()}.{file.filename.rsplit('.', 1)[1].lower()}"
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(file_path)
                        caption = new_image_captions[i] if i < len(new_image_captions) else ''
                        cursor.execute('''
                            INSERT INTO sow_images (sow_id, filename, original_name, caption)
                            VALUES (?, ?, ?, ?)
                        ''', (sow_id, filename, file.filename, caption))

                conn.commit()
            flash('SOW updated successfully!', 'success')
            return redirect(url_for('edit_sow_detail', sow_id=sow_id))
        
        except sqlite3.OperationalError as e:
            flash(f'Database error: {str(e)}', 'error')
            return redirect(url_for('edit_sow_detail', sow_id=sow_id))

    with sqlite3.connect('sow_database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sows WHERE id = ?', (sow_id,))
        sow = cursor.fetchone()
        if not sow:
            flash('SOW not found!', 'error')
            return redirect(url_for('edit_sows'))

        cursor.execute('SELECT * FROM charger_types ORDER BY name')
        charger_types = cursor.fetchall()
        
        cursor.execute('SELECT * FROM sow_images WHERE sow_id = ? ORDER BY uploaded_at', (sow_id,))
        images = cursor.fetchall()

    return render_template('edit_sow.html', sow=sow, charger_types=charger_types, images=images)

@app.route('/edit_sows')
def edit_sows():
    with sqlite3.connect('sow_database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, ct.name AS charger_type_name, c.name AS customer_name
            FROM sows s
            JOIN charger_types ct ON s.charger_type_id = ct.id
            LEFT JOIN customers c ON s.customer_id = c.id
            ORDER BY s.created_at DESC
        ''')
        sows = cursor.fetchall()
    return render_template('edit_sows.html', sows=sows)

@app.route('/delete_sow/<int:sow_id>', methods=['POST'])
def delete_sow(sow_id):
    try:
        with sqlite3.connect('sow_database.db') as conn:
            conn.execute('PRAGMA journal_mode=WAL;')
            cursor = conn.cursor()
            
            # Get image filenames to delete from the file system
            cursor.execute('SELECT filename FROM sow_images WHERE sow_id = ?', (sow_id,))
            images = cursor.fetchall()
            
            # Delete the SOW and associated images from the database
            cursor.execute('DELETE FROM sows WHERE id = ?', (sow_id,))
            conn.commit()
            
            # Delete image files from the server
            for img in images:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], img[0])
                if os.path.exists(file_path):
                    os.remove(file_path)
        flash('SOW and all associated images deleted successfully!', 'success')
    except sqlite3.Error as e:
        flash(f"An error occurred: {e}", 'error')
    return redirect(url_for('edit_sows'))

@app.route('/delete_image/<int:sow_id>/<filename>', methods=['POST'])
def delete_image(sow_id, filename):
    try:
        with sqlite3.connect('sow_database.db') as conn:
            conn.execute('PRAGMA journal_mode=WAL;')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM sow_images WHERE sow_id = ? AND filename = ?', (sow_id, filename))
            conn.commit()
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        return jsonify(success=True)
    except sqlite3.Error as e:
        return jsonify(success=False, error=str(e))

@app.route('/get_sow_content/<int:sow_id>')
def get_sow_content(sow_id):
    with sqlite3.connect('sow_database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sows WHERE id = ?', (sow_id,))
        sow = cursor.fetchone()
        if sow:
            return jsonify(dict(sow))
        return jsonify({})

@app.route('/get_sows/<int:charger_type_id>')
def get_sows_by_charger(charger_type_id):
    with sqlite3.connect('sow_database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sows WHERE charger_type_id = ?', (charger_type_id,))
        sows = cursor.fetchall()
    return jsonify([dict(s) for s in sows])

@app.route('/get_sow_images/<int:sow_id>')
def get_sow_images(sow_id):
    with sqlite3.connect('sow_database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT id, filename, original_name, caption FROM sow_images WHERE sow_id = ?', (sow_id,))
        images = cursor.fetchall()
    return jsonify([dict(img) for img in images])

@app.route('/get_customer/<int:customer_id>')
def get_customer(customer_id):
    with sqlite3.connect('sow_database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM customers WHERE id = ?', (customer_id,))
        customer = cursor.fetchone()
        if customer:
            return jsonify(dict(customer))
        return jsonify({})

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

            # Create PDF
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            doc = SimpleDocTemplate(temp_file.name, pagesize=letter)
            styles = getSampleStyleSheet()

            # Define custom styles
            styles.add(ParagraphStyle(name='TitleStyle', fontSize=24, spaceAfter=12, alignment=TA_CENTER, fontName='Helvetica-Bold'))
            styles.add(ParagraphStyle(name='HeadingStyle', fontSize=14, spaceAfter=6, fontName='Helvetica-Bold', leading=18))
            styles.add(ParagraphStyle(name='NormalStyle', fontSize=12, spaceAfter=12, leading=14))
            styles.add(ParagraphStyle(name='CaptionStyle', fontSize=10, textColor=colors.grey, spaceBefore=4, spaceAfter=12, alignment=TA_CENTER))

            story = []

            # Add SOW title
            if sow_data['title']:
                story.append(Paragraph(sow_data['title'], styles['TitleStyle']))
                story.append(Spacer(1, 0.25 * inch))

            # Add SOW content
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

            # Add Customer Check-in/Check-out Information
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

            # Add images and captions at the very end
            if image_data:
                story.append(PageBreak())
                story.append(Paragraph('REFERENCE IMAGES', styles['HeadingStyle']))
                story.append(Spacer(1, 0.2 * inch))
                for img in image_data:
                    image_path = os.path.join(app.config['UPLOAD_FOLDER'], img['filename'])
                    if os.path.exists(image_path):
                        if img['filename'].lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                            # Handle images
                            try:
                                # Scale image to fit within page width
                                rl_img = RLImage(image_path)
                                img_width, img_height = rl_img._origW, rl_img._origH
                                max_width = letter[0] - 2 * inch
                                if img_width > max_width:
                                    img_height = img_height * (max_width / img_width)
                                    img_width = max_width
                                
                                rl_img.drawWidth = img_width
                                rl_img.drawHeight = img_height
                                story.append(rl_img)
                                
                                # Add caption
                                if img['caption']:
                                    story.append(Paragraph(img['caption'], styles['CaptionStyle']))
                                else:
                                    # Use original filename as caption if none provided
                                    story.append(Paragraph(img['original_name'], styles['CaptionStyle']))
                                story.append(Spacer(1, 0.2 * inch))
                            except Exception as e:
                                story.append(Paragraph(f'<i>Error displaying image: {img["original_name"]}</i>', styles['NormalStyle']))
                                story.append(Spacer(1, 0.2 * inch))
                        elif img['filename'].lower().endswith('.pdf'):
                            # Handle PDF "images" by adding a reference
                            story.append(Paragraph(f'<b>Reference Document:</b> {img["original_name"]}', styles['NormalStyle']))
                            story.append(Paragraph(f'<i>{img["caption"]}</i>' if img['caption'] else '', styles['CaptionStyle']))
                            story.append(Spacer(1, 0.2 * inch))

            doc.build(story)
            temp_file.seek(0)
            return send_file(temp_file, as_attachment=True, download_name=f'SOW-{sow_data["title"]}.pdf')

    except Exception as e:
        flash(f'An error occurred during PDF generation: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/settings')
def settings():
    with sqlite3.connect('sow_database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM charger_types ORDER BY name')
        charger_types = cursor.fetchall()
        cursor.execute('SELECT * FROM customers ORDER BY name')
        customers = cursor.fetchall()
    return render_template('settings.html', charger_types=charger_types, customers=customers)

@app.route('/add_customer', methods=['GET', 'POST'])
def add_customer():
    if request.method == 'POST':
        customer_name = request.form['customer_name']
        check_in_contact = request.form.get('check_in_contact')
        check_in_phone = request.form.get('check_in_phone')
        check_in_instructions = request.form.get('check_in_instructions')
        check_out_contact = request.form.get('check_out_contact')
        check_out_phone = request.form.get('check_out_phone')
        check_out_instructions = request.form.get('check_out_instructions')

        try:
            with sqlite3.connect('sow_database.db') as conn:
                conn.execute('PRAGMA journal_mode=WAL;')
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO customers (name, check_in_contact, check_in_phone, check_in_instructions, check_out_contact, check_out_phone, check_out_instructions)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (customer_name, check_in_contact, check_in_phone, check_in_instructions, check_out_contact, check_out_phone, check_out_instructions))
                conn.commit()
            flash('Customer added successfully!', 'success')
            return redirect(url_for('settings'))
        except sqlite3.IntegrityError:
            flash('Error: A customer with this name already exists.', 'error')
            return render_template('add_customer.html')

    return render_template('add_customer.html')

@app.route('/edit_customer/<int:customer_id>', methods=['GET', 'POST'])
def edit_customer(customer_id):
    with sqlite3.connect('sow_database.db') as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM customers WHERE id = ?', (customer_id,))
        customer = cursor.fetchone()
        if not customer:
            flash('Customer not found!', 'error')
            return redirect(url_for('settings'))

    if request.method == 'POST':
        customer_name = request.form['customer_name']
        check_in_contact = request.form.get('check_in_contact')
        check_in_phone = request.form.get('check_in_phone')
        check_in_instructions = request.form.get('check_in_instructions')
        check_out_contact = request.form.get('check_out_contact')
        check_out_phone = request.form.get('check_out_phone')
        check_out_instructions = request.form.get('check_out_instructions')
        
        try:
            with sqlite3.connect('sow_database.db') as conn:
                conn.execute('PRAGMA journal_mode=WAL;')
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE customers SET
                        name = ?,
                        check_in_contact = ?,
                        check_in_phone = ?,
                        check_in_instructions = ?,
                        check_out_contact = ?,
                        check_out_phone = ?,
                        check_out_instructions = ?
                    WHERE id = ?
                ''', (customer_name, check_in_contact, check_in_phone, check_in_instructions, check_out_contact, check_out_phone, check_out_instructions, customer_id))
                conn.commit()
            flash('Customer updated successfully!', 'success')
            return redirect(url_for('settings'))
        except sqlite3.IntegrityError:
            flash('Error: A customer with this name already exists.', 'error')
            return render_template('edit_customer.html', customer=customer)
            
    return render_template('edit_customer.html', customer=customer)

@app.route('/delete_customer/<int:customer_id>', methods=['POST'])
def delete_customer(customer_id):
    try:
        with sqlite3.connect('sow_database.db') as conn:
            conn.execute('PRAGMA journal_mode=WAL;')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM customers WHERE id = ?', (customer_id,))
            conn.commit()
        flash('Customer deleted successfully!', 'success')
    except sqlite3.Error as e:
        flash(f"An error occurred: {e}", 'error')
    return redirect(url_for('settings'))

@app.route('/add_charger_type', methods=['POST'])
def add_charger_type():
    name = request.form['charger_type_name']
    try:
        with sqlite3.connect('sow_database.db') as conn:
            conn.execute('PRAGMA journal_mode=WAL;')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO charger_types (name) VALUES (?)', (name,))
            conn.commit()
        flash('Charger type added successfully!', 'success')
    except sqlite3.IntegrityError:
        flash('Error: This charger type already exists.', 'error')
    return redirect(url_for('settings'))

@app.route('/delete_charger_type/<int:charger_type_id>', methods=['POST'])
def delete_charger_type(charger_type_id):
    try:
        with sqlite3.connect('sow_database.db') as conn:
            conn.execute('PRAGMA journal_mode=WAL;')
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM sows WHERE charger_type_id = ?', (charger_type_id,))
            sow_count = cursor.fetchone()[0]
            if sow_count > 0:
                flash('Cannot delete charger type with associated SOWs. Please delete all SOWs for this type first.', 'error')
            else:
                cursor.execute('DELETE FROM charger_types WHERE id = ?', (charger_type_id,))
                conn.commit()
                flash('Charger type deleted successfully!', 'success')
    except sqlite3.Error as e:
        flash(f"An error occurred: {e}", 'error')
    return redirect(url_for('settings'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
