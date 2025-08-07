# Enhanced database schema and backend modifications for comprehensive meme classification

import os
import sqlite3
import random
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session, abort
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
    """Initialize the enhanced database with comprehensive meme classification"""
    conn = sqlite3.connect('memes2.db')
    cursor = conn.cursor()
    
    # Enhanced memes table with comprehensive classification
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            
            -- Contributor Information
            contributor_name TEXT,
            contributor_email TEXT,
            country_of_submission TEXT NOT NULL,
            platform_found TEXT NOT NULL,
            uploader_session TEXT,
            
            -- Content Classification
            meme_content TEXT NOT NULL,
            meme_template TEXT,
            estimated_year TEXT NOT NULL,
            cultural_reach TEXT NOT NULL,
            niche_community TEXT,
            
            -- Humor & Emotional Analysis
            humor_explanation TEXT NOT NULL,
            humor_type TEXT NOT NULL,
            emotions_conveyed TEXT NOT NULL, -- JSON array of selected emotions
            
            -- Context & References
            cultural_references TEXT,
            context_required TEXT NOT NULL,
            age_group_target TEXT,
            
            -- AI Training Descriptions
            description_1 TEXT NOT NULL,
            description_2 TEXT NOT NULL,
            description_3 TEXT NOT NULL,
            description_4 TEXT NOT NULL,
            correct_description INTEGER NOT NULL, -- 1-4 indicating which is correct
            
            -- Additional Data
            additional_notes TEXT,
            terms_agreement BOOLEAN NOT NULL DEFAULT 0,
            
            -- Metadata
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Enhanced evaluations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            meme_id INTEGER NOT NULL,
            chosen_description INTEGER NOT NULL,
            was_correct BOOLEAN, -- Whether the chosen description was the correct one
            evaluation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            evaluation_time_seconds INTEGER, -- Time spent on evaluation
            FOREIGN KEY (meme_id) REFERENCES memes (id)
        )
    ''')
    
    # User contributors table (for registered users)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contributors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            country TEXT,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_submissions INTEGER DEFAULT 0,
            total_evaluations INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Analytics table for research insights
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meme_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meme_id INTEGER NOT NULL,
            total_evaluations INTEGER DEFAULT 0,
            correct_identifications INTEGER DEFAULT 0,
            accuracy_rate REAL DEFAULT 0.0,
            avg_evaluation_time REAL DEFAULT 0.0,
            difficulty_score REAL DEFAULT 0.0, -- Based on accuracy rate
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meme_id) REFERENCES memes (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('memes.db')
    conn.row_factory = sqlite3.Row
    return conn

def update_meme_analytics(meme_id, was_correct, evaluation_time):
    """Update analytics data when a new evaluation is submitted"""
    conn = get_db_connection()
    
    # Get or create analytics record
    analytics = conn.execute(
        'SELECT * FROM meme_analytics WHERE meme_id = ?', 
        (meme_id,)
    ).fetchone()
    
    if analytics:
        # Update existing record
        new_total = analytics['total_evaluations'] + 1
        new_correct = analytics['correct_identifications'] + (1 if was_correct else 0)
        new_accuracy = new_correct / new_total if new_total > 0 else 0
        
        # Calculate moving average of evaluation time
        current_avg_time = analytics['avg_evaluation_time']
        new_avg_time = ((current_avg_time * analytics['total_evaluations']) + evaluation_time) / new_total
        
        # Calculate difficulty score (inverse of accuracy, 0-1 scale)
        difficulty_score = 1 - new_accuracy
        
        conn.execute('''
            UPDATE meme_analytics 
            SET total_evaluations = ?, correct_identifications = ?, 
                accuracy_rate = ?, avg_evaluation_time = ?, difficulty_score = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE meme_id = ?
        ''', (new_total, new_correct, new_accuracy, new_avg_time, difficulty_score, meme_id))
    else:
        # Create new analytics record
        accuracy_rate = 1.0 if was_correct else 0.0
        difficulty_score = 1.0 - accuracy_rate
        
        conn.execute('''
            INSERT INTO meme_analytics 
            (meme_id, total_evaluations, correct_identifications, accuracy_rate, 
             avg_evaluation_time, difficulty_score) 
            VALUES (?, 1, ?, ?, ?, ?)
        ''', (meme_id, 1 if was_correct else 0, accuracy_rate, evaluation_time, difficulty_score))
    
    conn.commit()
    conn.close()

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
    
    # Validate page number is positive
    if page < 1:
        abort(404)
    
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    
    # Get total count for pagination
    total_count = conn.execute('SELECT COUNT(*) as count FROM memes').fetchone()['count']
    
    # Check if page is out of range
    max_page = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    if page > max_page and total_count > 0:
        abort(404)
    
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

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """Enhanced upload with comprehensive meme classification"""
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
        
        # Validate file
        if file.filename == '' or not (file and allowed_file(file.filename)):
            flash('Please select a valid image file (PNG, JPG, JPEG, or GIF).')
            return redirect(request.url)
        
        # Extract all form data
        form_data = {
            # Contributor Information
            'contributor_name': request.form.get('contributor_name', '').strip(),
            'contributor_email': request.form.get('contributor_email', '').strip(),
            'country_of_submission': request.form.get('country_of_submission', '').strip(),
            'platform_found': request.form.get('platform_found', '').strip(),
            
            # Content Classification
            'meme_content': request.form.get('meme_content', '').strip(),
            'meme_template': request.form.get('meme_template', '').strip(),
            'estimated_year': request.form.get('estimated_year', '').strip(),
            'cultural_reach': request.form.get('cultural_reach', '').strip(),
            'niche_community': request.form.get('niche_community', '').strip(),
            
            # Humor & Emotional Analysis
            'humor_explanation': request.form.get('humor_explanation', '').strip(),
            'humor_type': request.form.get('humor_type', '').strip(),
            'emotions': request.form.getlist('emotions'),
            
            # Context & References
            'cultural_references': request.form.get('cultural_references', '').strip(),
            'context_required': request.form.get('context_required', '').strip(),
            'age_group_target': request.form.get('age_group_target', '').strip(),
            
            # AI Training Descriptions
            'description_1': request.form.get('description_1', '').strip(),
            'description_2': request.form.get('description_2', '').strip(),
            'description_3': request.form.get('description_3', '').strip(),
            'description_4': request.form.get('description_4', '').strip(),
            'correct_description': request.form.get('correct_description', ''),
            
            # Additional Data
            'additional_notes': request.form.get('additional_notes', '').strip(),
            'terms_agreement': request.form.get('terms_agreement') == 'on'
        }
        
        # Validate required fields
        required_fields = [
            'country_of_submission', 'platform_found', 'meme_content', 'estimated_year',
            'cultural_reach', 'humor_explanation', 'humor_type', 'context_required',
            'description_1', 'description_2', 'description_3', 'description_4', 'correct_description'
        ]
        
        missing_fields = [field for field in required_fields if not form_data[field]]
        
        if missing_fields:
            flash(f'Please fill in all required fields: {", ".join(missing_fields)}')
            return redirect(request.url)
        
        # Validate emotions (at least one must be selected)
        if not form_data['emotions']:
            flash('Please select at least one emotion that the meme conveys.')
            return redirect(request.url)
        
        # Validate correct_description is between 1-4
        try:
            correct_desc = int(form_data['correct_description'])
            if correct_desc not in [1, 2, 3, 4]:
                raise ValueError()
        except (ValueError, TypeError):
            flash('Please indicate which description is correct (1-4).')
            return redirect(request.url)
        
        # Validate terms agreement
        if not form_data['terms_agreement']:
            flash('Please agree to the terms before submitting.')
            return redirect(request.url)
        
        # Validate niche community if cultural reach is "Niche"
        if form_data['cultural_reach'] == 'Niche' and not form_data['niche_community']:
            flash('Please specify the niche community since you selected "Niche" for cultural reach.')
            return redirect(request.url)
        
        # Process and save file
        original_filename = secure_filename(file.filename)
        unique_filename = str(uuid.uuid4()) + '_' + original_filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        
        if 'session_id' not in session:
            session['session_id'] = str(uuid.uuid4())
        
        # Convert emotions list to JSON
        emotions_json = json.dumps(form_data['emotions'])
        
        # Save to database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO memes (
                filename, original_filename, contributor_name, contributor_email,
                country_of_submission, platform_found, uploader_session,
                meme_content, meme_template, estimated_year, cultural_reach, niche_community,
                humor_explanation, humor_type, emotions_conveyed,
                cultural_references, context_required, age_group_target,
                description_1, description_2, description_3, description_4, correct_description,
                additional_notes, terms_agreement
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            unique_filename, original_filename, form_data['contributor_name'], form_data['contributor_email'],
            form_data['country_of_submission'], form_data['platform_found'], session['session_id'],
            form_data['meme_content'], form_data['meme_template'], form_data['estimated_year'], 
            form_data['cultural_reach'], form_data['niche_community'],
            form_data['humor_explanation'], form_data['humor_type'], emotions_json,
            form_data['cultural_references'], form_data['context_required'], form_data['age_group_target'],
            form_data['description_1'], form_data['description_2'], form_data['description_3'], 
            form_data['description_4'], correct_desc,
            form_data['additional_notes'], form_data['terms_agreement']
        ))
        
        meme_id = cursor.lastrowid
        
        # Update contributor stats if email provided
        if form_data['contributor_email']:
            cursor.execute('''
                INSERT OR IGNORE INTO contributors (name, email, country) 
                VALUES (?, ?, ?)
            ''', (form_data['contributor_name'], form_data['contributor_email'], form_data['country_of_submission']))
            
            cursor.execute('''
                UPDATE contributors 
                SET total_submissions = total_submissions + 1,
                    name = COALESCE(?, name),
                    country = COALESCE(?, country)
                WHERE email = ?
            ''', (form_data['contributor_name'], form_data['country_of_submission'], form_data['contributor_email']))
        
        conn.commit()
        conn.close()
        
        flash('Meme uploaded and classified successfully! Thank you for your detailed contribution to our research.')
        return redirect(url_for('gallery'))
    
    return render_template('upload_enhanced.html')

@app.route('/submit_evaluation', methods=['POST'])
def submit_evaluation():
    """Enhanced evaluation submission with correctness tracking"""
    meme_id = request.form.get('meme_id')
    chosen_description = request.form.get('chosen_description')
    evaluation_time = request.form.get('evaluation_time', 0, type=int)  # Time in seconds
    
    if not meme_id or not chosen_description:
        flash('Please select a description.')
        return redirect(url_for('evaluate'))
    
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    # Get the meme to check correct answer
    conn = get_db_connection()
    meme = conn.execute('SELECT correct_description FROM memes WHERE id = ?', (meme_id,)).fetchone()
    
    if not meme:
        flash('Meme not found.')
        return redirect(url_for('evaluate'))
    
    # Check if the chosen description is correct
    was_correct = int(chosen_description) == meme['correct_description']
    
    # Save evaluation
    conn.execute(
        '''INSERT INTO evaluations 
           (session_id, meme_id, chosen_description, was_correct, evaluation_time_seconds) 
           VALUES (?, ?, ?, ?, ?)''',
        (session['session_id'], meme_id, chosen_description, was_correct, evaluation_time)
    )
    conn.commit()
    conn.close()
    
    # Update analytics
    update_meme_analytics(meme_id, was_correct, evaluation_time)
    
    evaluation_count = get_user_evaluation_count()
    
    # Provide feedback on correctness
    if was_correct:
        flash(f'✅ Correct! You identified the best description. Progress: {evaluation_count}/10')
    else:
        flash(f'❌ Not quite right, but thanks for participating! Progress: {evaluation_count}/10')
    
    if evaluation_count >= 10:
        flash('🎉 Congratulations! You have completed all 10 evaluations. You can now upload your own meme!')
        return redirect(url_for('upload_file'))
    else:
        return redirect(url_for('evaluate'))
    

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


@app.route('/analytics')
def analytics():
    """Research analytics dashboard"""
    conn = get_db_connection()
    
    # Basic stats
    total_memes = conn.execute('SELECT COUNT(*) as count FROM memes').fetchone()['count']
    total_evaluations = conn.execute('SELECT COUNT(*) as count FROM evaluations').fetchone()['count']
    unique_evaluators = conn.execute('SELECT COUNT(DISTINCT session_id) as count FROM evaluations').fetchone()['count']
    registered_contributors = conn.execute('SELECT COUNT(*) as count FROM contributors WHERE email IS NOT NULL').fetchone()['count']
    
    # Accuracy statistics
    accuracy_stats = conn.execute('''
        SELECT 
            AVG(CASE WHEN was_correct THEN 1.0 ELSE 0.0 END) as overall_accuracy,
            COUNT(CASE WHEN was_correct THEN 1 END) as correct_evaluations,
            COUNT(*) as total_evaluations
        FROM evaluations
    ''').fetchone()
    
    # Country distribution
    country_stats = conn.execute('''
        SELECT country_of_submission, COUNT(*) as count 
        FROM memes 
        GROUP BY country_of_submission 
        ORDER BY count DESC 
        LIMIT 10
    ''').fetchall()
    
    # Platform distribution
    platform_stats = conn.execute('''
        SELECT platform_found, COUNT(*) as count 
        FROM memes 
        GROUP BY platform_found 
        ORDER BY count DESC
    ''').fetchall()
    
    # Humor type distribution
    humor_stats = conn.execute('''
        SELECT humor_type, COUNT(*) as count 
        FROM memes 
        GROUP BY humor_type 
        ORDER BY count DESC
    ''').fetchall()
    
    # Cultural reach distribution
    cultural_stats = conn.execute('''
        SELECT cultural_reach, COUNT(*) as count 
        FROM memes 
        GROUP BY cultural_reach 
        ORDER BY count DESC
    ''').fetchall()
    
    # Most difficult memes (lowest accuracy)
    difficult_memes = conn.execute('''
        SELECT m.id, m.original_filename, m.meme_content, a.accuracy_rate, a.total_evaluations
        FROM memes m
        JOIN meme_analytics a ON m.id = a.meme_id
        WHERE a.total_evaluations >= 5
        ORDER BY a.accuracy_rate ASC
        LIMIT 10
    ''').fetchall()
    
    # Easiest memes (highest accuracy)
    easy_memes = conn.execute('''
        SELECT m.id, m.original_filename, m.meme_content, a.accuracy_rate, a.total_evaluations
        FROM memes m
        JOIN meme_analytics a ON m.id = a.meme_id
        WHERE a.total_evaluations >= 5
        ORDER BY a.accuracy_rate DESC
        LIMIT 10
    ''').fetchall()
    
    conn.close()
    
    return render_template('analytics.html',
                         total_memes=total_memes,
                         total_evaluations=total_evaluations,
                         unique_evaluators=unique_evaluators,
                         registered_contributors=registered_contributors,
                         accuracy_stats=accuracy_stats,
                         country_stats=country_stats,
                         platform_stats=platform_stats,
                         humor_stats=humor_stats,
                         cultural_stats=cultural_stats,
                         difficult_memes=difficult_memes,
                         easy_memes=easy_memes)

@app.route('/export_data')
def export_data():
    """Export research data (for researchers)"""
    if not DEVELOPMENT:  # Add proper authentication in production
        abort(403)
    
    conn = get_db_connection()
    
    # Get all meme data with analytics
    memes_data = conn.execute('''
        SELECT m.*, a.accuracy_rate, a.total_evaluations as analytics_evaluations,
               a.difficulty_score, a.avg_evaluation_time
        FROM memes m
        LEFT JOIN meme_analytics a ON m.id = a.meme_id
        ORDER BY m.upload_date DESC
    ''').fetchall()
    
    # Get all evaluation data
    evaluations_data = conn.execute('''
        SELECT e.*, m.correct_description, m.cultural_reach, m.humor_type
        FROM evaluations e
        JOIN memes m ON e.meme_id = m.id
        ORDER BY e.evaluation_date DESC
    ''').fetchall()
    
    conn.close()
    
    # Convert to JSON for easy export
    memes_json = []
    for meme in memes_data:
        meme_dict = dict(meme)
        # Parse emotions JSON
        if meme_dict['emotions_conveyed']:
            try:
                meme_dict['emotions_conveyed'] = json.loads(meme_dict['emotions_conveyed'])
            except:
                meme_dict['emotions_conveyed'] = []
        memes_json.append(meme_dict)
    
    evaluations_json = [dict(eval) for eval in evaluations_data]
    
    export_data = {
        'export_timestamp': datetime.now().isoformat(),
        'memes': memes_json,
        'evaluations': evaluations_json,
        'summary': {
            'total_memes': len(memes_json),
            'total_evaluations': len(evaluations_json)
        }
    }
    
    from flask import jsonify
    return jsonify(export_data)

# Add the remaining helper functions
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
    """Get count of memes available for evaluation"""
    conn = get_db_connection()
    count = conn.execute('SELECT COUNT(*) as count FROM memes').fetchone()['count']
    conn.close()
    return count

def can_user_upload():
    """Check if user can upload"""
    evaluation_count = get_user_evaluation_count()
    available_memes = get_available_memes_count()
    return evaluation_count >= 10 or available_memes < 10

def get_random_meme_for_evaluation():
    """Get a random meme that the user hasn't evaluated yet"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    conn = get_db_connection()
    meme = conn.execute('''
        SELECT * FROM memes 
        WHERE id NOT IN (
            SELECT meme_id FROM evaluations WHERE session_id = ?
        ) ORDER BY RANDOM() LIMIT 1
    ''', (session['session_id'],)).fetchone()
    
    conn.close()
    return meme

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors - Page not found"""
    print(f"404 ERROR HANDLER CALLED: {error}")  # Debug print
    app.logger.error(f'404 error: {error}')
    
    # Try the simple template first to debug
    try:
        return render_template('404.html'), 404
    except Exception as e:
        print(f"Template rendering error: {e}")
        # Fallback to a basic HTML response
        return """
        <!DOCTYPE html>
        <html>
        <head><title>404 Not Found</title></head>
        <body>
            <h1>404 - Page Not Found</h1>
            <p>The page you requested could not be found.</p>
            <a href="/">Go Home</a>
        </body>
        </html>
        """, 404
    
@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors - Internal server error"""
    app.logger.error(f'500 error: {error}')  # Add logging
    # No rollback needed for sqlite3 connection
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 errors - Forbidden access"""
    app.logger.error(f'403 error: {error}')  # Add logging
    return render_template('403.html'), 403

@app.errorhandler(413)
def too_large_error(error):
    """Handle 413 errors - File too large"""
    app.logger.error(f'413 error: {error}')  # Add logging
    return render_template('413.html'), 413

if __name__ == '__main__':
    init_db()
    app.run()