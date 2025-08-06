import os
import sqlite3
import random
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
import uuid
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Environment detection
DEVELOPMENT = os.environ.get('ENV') == 'development' or app.debug
print({os.environ.get('ENV')})
print(f"Running in {'development' if DEVELOPMENT else 'production'} mode")

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    """Initialize the database"""
    conn = sqlite3.connect('memes.db')
    cursor = conn.cursor()
    
    # Memes table with 4 descriptions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            description_1 TEXT,
            description_2 TEXT,
            description_3 TEXT,
            description_4 TEXT,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            uploader_session TEXT
        )
    ''')
    
    # Evaluations table to track user evaluations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            meme_id INTEGER NOT NULL,
            chosen_description INTEGER NOT NULL,
            evaluation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meme_id) REFERENCES memes (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('memes.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_user_evaluation_count():
    """Get number of evaluations completed by current session"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    conn = get_db_connection()
    count = conn.execute(
        'SELECT COUNT(*) as count FROM evaluations WHERE session_id = ?',
        (session['session_id'],)
    ).fetchone()['count']
    conn.close()
    return count

def get_available_memes_count():
    """Get count of memes available for evaluation (with all 4 descriptions)"""
    conn = get_db_connection()
    count = conn.execute('''
        SELECT COUNT(*) as count FROM memes 
        WHERE description_1 IS NOT NULL 
          AND description_2 IS NOT NULL 
          AND description_3 IS NOT NULL 
          AND description_4 IS NOT NULL
    ''').fetchone()['count']
    conn.close()
    return count

def can_user_upload():
    """Check if user can upload - either completed 10 evaluations OR there are <10 memes available"""
    evaluation_count = get_user_evaluation_count()
    available_memes = get_available_memes_count()
    
    # Allow upload if: completed 10 evaluations OR there are fewer than 10 memes to evaluate
    return evaluation_count >= 10 or available_memes < 10

def get_random_meme_for_evaluation():
    """Get a random meme that the user hasn't evaluated yet"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    conn = get_db_connection()
    
    # Get memes that this session hasn't evaluated yet and have all 4 descriptions
    meme = conn.execute('''
        SELECT * FROM memes 
        WHERE id NOT IN (
            SELECT meme_id FROM evaluations WHERE session_id = ?
        ) AND description_1 IS NOT NULL 
          AND description_2 IS NOT NULL 
          AND description_3 IS NOT NULL 
          AND description_4 IS NOT NULL
        ORDER BY RANDOM() 
        LIMIT 1
    ''', (session['session_id'],)).fetchone()
    
    conn.close()
    return meme

# Pagination helper class
class Pagination:
    def __init__(self, page, per_page, total_count):
        self.page = page
        self.per_page = per_page
        self.total_count = total_count
    
    @property
    def items(self):
        return self._items
    
    @items.setter
    def items(self, value):
        self._items = value
    
    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None
    
    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None
    
    @property
    def has_prev(self):
        return self.page > 1
    
    @property
    def has_next(self):
        return self.page < self.pages
    
    @property
    def pages(self):
        return int((self.total_count - 1) / self.per_page) + 1 if self.total_count > 0 else 1
    
    @property
    def total(self):
        return self.total_count
    
    @property
    def first(self):
        return ((self.page - 1) * self.per_page) + 1 if self.total_count > 0 else 0
    
    @property
    def last(self):
        return min(self.first + self.per_page - 1, self.total_count)
    
    def iter_pages(self, left_edge=2, left_current=2, right_current=3, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (self.page - left_current - 1 < num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num

@app.route('/')
def index():
    """Landing page with intro and evaluation count"""
    evaluation_count = get_user_evaluation_count()
    available_memes = get_available_memes_count()
    can_upload = can_user_upload()
    
    return render_template('index.html', 
                         evaluation_count=evaluation_count, 
                         available_memes=available_memes,
                         can_upload=can_upload,
                         development=DEVELOPMENT)

@app.route('/gallery')
def gallery():
    """Display uploaded memes with enhanced pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 4, type=int)
    
    # Limit per_page options for security - changed to 4, 8, 16
    if per_page not in [4, 8, 16]:
        per_page = 4
    
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    
    # Get total count for pagination
    total_count = conn.execute('SELECT COUNT(*) as count FROM memes').fetchone()['count']
    
    # Get memes for current page
    memes = conn.execute(
        'SELECT * FROM memes ORDER BY upload_date DESC LIMIT ? OFFSET ?',
        (per_page, offset)
    ).fetchall()
    
    conn.close()
    
    # Create pagination object
    pagination = Pagination(page, per_page, total_count)
    pagination.items = memes
    
    return render_template('gallery.html', 
                         memes=pagination,
                         per_page=per_page)

@app.route('/evaluate')
def evaluate():
    """Show meme evaluation page"""
    evaluation_count = get_user_evaluation_count()
    available_memes = get_available_memes_count()
    
    if evaluation_count >= 10:
        flash('You have completed all required evaluations! You can now upload memes.')
        return redirect(url_for('upload_file'))
    
    if available_memes < 10:
        flash(f'Only {available_memes} memes available for evaluation. You can upload without completing 10 evaluations!')
        return redirect(url_for('upload_file'))
    
    meme = get_random_meme_for_evaluation()
    
    if not meme:
        flash('No more memes available for evaluation. You can now upload your own!')
        return redirect(url_for('upload_file'))
    
    # Randomize the order of descriptions for fair evaluation
    descriptions = [
        (1, meme['description_1']),
        (2, meme['description_2']),
        (3, meme['description_3']),
        (4, meme['description_4'])
    ]
    random.shuffle(descriptions)
    
    return render_template('evaluate.html', 
                         meme=meme, 
                         descriptions=descriptions,
                         evaluation_count=evaluation_count)

@app.route('/submit_evaluation', methods=['POST'])
def submit_evaluation():
    """Submit an evaluation"""
    meme_id = request.form.get('meme_id')
    chosen_description = request.form.get('chosen_description')
    
    if not meme_id or not chosen_description:
        flash('Please select a description.')
        return redirect(url_for('evaluate'))
    
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    # Save evaluation
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO evaluations (session_id, meme_id, chosen_description) VALUES (?, ?, ?)',
        (session['session_id'], meme_id, chosen_description)
    )
    conn.commit()
    conn.close()
    
    evaluation_count = get_user_evaluation_count()
    
    if evaluation_count >= 10:
        flash('Congratulations! You have completed all 10 evaluations. You can now upload your own meme!')
        return redirect(url_for('upload_file'))
    else:
        flash(f'Evaluation submitted! Progress: {evaluation_count}/10')
        return redirect(url_for('evaluate'))

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """Upload meme with 4 descriptions"""
    evaluation_count = get_user_evaluation_count()
    available_memes = get_available_memes_count()
    
    if not can_user_upload():
        remaining_evaluations = 10 - evaluation_count
        flash(f'You need to complete {remaining_evaluations} more evaluations before you can upload.')
        return redirect(url_for('evaluate'))
    
    if request.method == 'POST':
        # Check if file was uploaded
        if 'file' not in request.files:
            flash('No file selected')
            return redirect(request.url)
        
        file = request.files['file']
        descriptions = [
            request.form.get('description_1', ''),
            request.form.get('description_2', ''),
            request.form.get('description_3', ''),
            request.form.get('description_4', '')
        ]
        
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        
        # Validate all descriptions are provided
        if not all(desc.strip() for desc in descriptions):
            flash('Please provide all 4 descriptions.')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            # Generate unique filename
            original_filename = secure_filename(file.filename)
            unique_filename = str(uuid.uuid4()) + '_' + original_filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            # Save file
            file.save(file_path)
            
            if 'session_id' not in session:
                session['session_id'] = str(uuid.uuid4())
            
            # Save to database
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO memes (filename, original_filename, description_1, description_2, 
                                 description_3, description_4, uploader_session) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (unique_filename, original_filename, descriptions[0], descriptions[1], 
                  descriptions[2], descriptions[3], session['session_id']))
            conn.commit()
            conn.close()
            
            flash('Meme uploaded successfully! Thank you for contributing to our benchmark.')
            return redirect(url_for('gallery'))
        else:
            flash('Invalid file type. Please upload PNG, JPG, JPEG, or GIF files.')
    
    return render_template('upload.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/stats')
def stats():
    """Show basic statistics"""
    conn = get_db_connection()
    
    total_memes = conn.execute('SELECT COUNT(*) as count FROM memes').fetchone()['count']
    total_evaluations = conn.execute('SELECT COUNT(*) as count FROM evaluations').fetchone()['count']
    unique_evaluators = conn.execute('SELECT COUNT(DISTINCT session_id) as count FROM evaluations').fetchone()['count']
    
    conn.close()
    
    return render_template('stats.html', 
                         total_memes=total_memes,
                         total_evaluations=total_evaluations,
                         unique_evaluators=unique_evaluators)

@app.route('/reset_session')
def reset_session():
    """Reset current session (for testing)"""
    if not DEVELOPMENT:
        flash('This feature is only available in development mode.')
        return redirect(url_for('index'))
    
    session.clear()
    flash('Session reset! You can now start fresh.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)