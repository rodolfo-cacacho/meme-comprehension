# Complete appv2.py with enhanced features and user system integration

import os
import sqlite3
import random
import json
from datetime import datetime,timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session, abort, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from dotenv import load_dotenv
import secrets
import hashlib
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
EMAIL_USER = os.environ.get('GMAIL_USER')
EMAIL_PW = os.environ.get('GMAIL_APP_PASSWORD')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Environment detection
DEVELOPMENT = os.environ.get('ENV') == 'development' or app.debug
print(f"Running in {'development' if DEVELOPMENT else 'production'} mode")

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MIN_MEME_COUNT = 5
EVAL_COUNT = 5  # Number of evaluations required to upload memes

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def add_evaluation_fields():
    """Add new fields for humor/emotion evaluation"""
    conn = sqlite3.connect('memes.db')
    cursor = conn.cursor()
    
    try:
        # Add new columns for humor/emotion evaluation
        new_eval_columns = [
            ('evaluated_humor_type', 'TEXT'),
            ('evaluated_emotions', 'TEXT'),  # JSON array
            ('evaluated_context_level', 'TEXT'),
            ('matches_humor_type', 'BOOLEAN'),
            ('emotion_overlap_score', 'REAL')  # 0.0-1.0 based on overlap
        ]
        
        for column_name, column_type in new_eval_columns:
            try:
                cursor.execute(f"ALTER TABLE evaluations ADD COLUMN {column_name} {column_type}")
                print(f"Added evaluation column: {column_name}")
            except sqlite3.OperationalError:
                pass  # Column already exists
        
        conn.commit()
        
    except Exception as e:
        print(f"Error adding evaluation fields: {e}")
        conn.rollback()
    finally:
        conn.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    """Initialize the enhanced database with comprehensive meme classification"""
    conn = sqlite3.connect('memes.db')
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
            contributor_country TEXT NOT NULL,
            meme_origin_country TEXT,
            platform_found TEXT NOT NULL,
            uploader_session TEXT,
            uploader_user_id INTEGER,
            
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
            meme_description TEXT NOT NULL,
            
            -- Additional Data
            additional_notes TEXT,
            terms_agreement BOOLEAN NOT NULL DEFAULT 0,
            
            -- Metadata
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (uploader_user_id) REFERENCES users (id)
        )
    ''')
    
    # Enhanced evaluations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            user_id INTEGER,
            meme_id INTEGER NOT NULL,
            chosen_description INTEGER NOT NULL,
            was_correct BOOLEAN, -- Whether the chosen description was the correct one
            confidence_level INTEGER DEFAULT 3, -- 1-4 confidence rating
            evaluation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            evaluation_time_seconds INTEGER, -- Time spent on evaluation
            evaluated_humor_type TEXT, -- Humor type evaluated by user
            evaluated_emotions, 'TEXT',  -- JSON array
            evaluated_context_level, 'TEXT',
            matches_humor_type, 'BOOLEAN',
            emotion_overlap_score, 'REAL', -- 0.0-1.0 based on overlap
            FOREIGN KEY (meme_id) REFERENCES memes (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Users table for registered contributors
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT, -- For future login functionality
            country TEXT,
            affiliation TEXT,
            research_interest TEXT,
            
            -- Notification preferences
            notify_updates BOOLEAN DEFAULT 1,
            notify_milestones BOOLEAN DEFAULT 1,
            data_access_interest BOOLEAN DEFAULT 0,
            
            -- Statistics
            total_submissions INTEGER DEFAULT 0,
            total_evaluations INTEGER DEFAULT 0,
            evaluation_accuracy REAL DEFAULT 0.0,
            
            -- Metadata
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
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
            avg_confidence_level REAL DEFAULT 0.0,
            difficulty_score REAL DEFAULT 0.0, -- Based on accuracy rate
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meme_id) REFERENCES memes (id)
        )
    ''')
    
    # User sessions table for anonymous users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            user_id INTEGER,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            evaluations_completed INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('memes.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_current_user():
    """Get current user if logged in, None otherwise"""
    if 'user_id' in session:
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        return user
    return None

def get_or_create_session():
    """Get or create session for anonymous users"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        
        # Store in database
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO user_sessions (session_id, user_id) VALUES (?, ?)',
            (session['session_id'], session.get('user_id'))
        )
        conn.commit()
        conn.close()
    
    return session['session_id']

def update_meme_analytics(meme_id, was_correct, evaluation_time, confidence_level=3):
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
        
        # Calculate moving average of confidence level
        current_avg_confidence = analytics['avg_confidence_level']
        new_avg_confidence = ((current_avg_confidence * analytics['total_evaluations']) + confidence_level) / new_total
        
        # Calculate difficulty score (inverse of accuracy, 0-1 scale)
        difficulty_score = 1 - new_accuracy
        
        conn.execute('''
            UPDATE meme_analytics 
            SET total_evaluations = ?, correct_identifications = ?, 
                accuracy_rate = ?, avg_evaluation_time = ?, avg_confidence_level = ?,
                difficulty_score = ?, last_updated = CURRENT_TIMESTAMP
            WHERE meme_id = ?
        ''', (new_total, new_correct, new_accuracy, new_avg_time, new_avg_confidence, difficulty_score, meme_id))
    else:
        # Create new analytics record
        accuracy_rate = 1.0 if was_correct else 0.0
        difficulty_score = 1.0 - accuracy_rate
        
        conn.execute('''
            INSERT INTO meme_analytics 
            (meme_id, total_evaluations, correct_identifications, accuracy_rate, 
             avg_evaluation_time, avg_confidence_level, difficulty_score) 
            VALUES (?, 1, ?, ?, ?, ?, ?)
        ''', (meme_id, 1 if was_correct else 0, accuracy_rate, evaluation_time, confidence_level, difficulty_score))
    
    conn.commit()
    conn.close()


def send_email_gmail(to_email, subject, body):
    sender_email = EMAIL_USER
    sender_password = EMAIL_PW  # Use App Password, not regular password
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

# Email sending (you can use different providers)
def send_email(to_email, subject, body):
    """
    Simple email sending function. 
    For development, just print the email. 
    For production, use services like SendGrid, Mailgun, or SMTP
    """
    if DEVELOPMENT:
        print("="*50)
        print(f"EMAIL TO: {to_email}")
        print(f"SUBJECT: {subject}")
        print(f"BODY:\n{body}")
        print("="*50)
        return True
    else:
        # TODO: Implement real email sending for production
        # Example with SendGrid:
        # import sendgrid
        # sg = sendgrid.SendGridAPIClient(api_key=os.environ.get('SENDGRID_API_KEY'))
        # ...
        print(f"Would send email to {to_email}: {subject}")
        send_email_gmail(to_email, subject, body) 
        return True

def generate_login_token(email):
    """Generate a secure login token for email"""
    # Create a token with timestamp
    timestamp = str(int(time.time()))
    random_part = secrets.token_urlsafe(32)
    
    # Combine email, timestamp, and random part
    token_data = f"{email}:{timestamp}:{random_part}"
    
    # Create a hash for verification
    secret_key = app.config['SECRET_KEY']
    token_hash = hashlib.sha256(f"{token_data}:{secret_key}".encode()).hexdigest()
    
    # Final token is base64 encoded
    import base64
    final_token = base64.urlsafe_b64encode(f"{token_data}:{token_hash}".encode()).decode()
    
    return final_token

def verify_login_token(token, email):
    """Verify a login token is valid"""
    try:
        import base64
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(':')
        
        if len(parts) != 4:
            return False
        
        token_email, timestamp, random_part, token_hash = parts
        
        # Check email matches
        if token_email != email:
            return False
        
        # Check token is not too old (24 hours)
        token_time = int(timestamp)
        if time.time() - token_time > 24 * 60 * 60:
            return False
        
        # Verify hash
        secret_key = app.config['SECRET_KEY']
        expected_hash = hashlib.sha256(f"{token_email}:{timestamp}:{random_part}:{secret_key}".encode()).hexdigest()
        
        return token_hash == expected_hash
        
    except Exception as e:
        print(f"Token verification error: {e}")
        return False
    
@app.context_processor
def inject_app_info():
    """Make app info available to all templates"""
    try:
        # Get the modification time of the current app file
        app_file = __file__  # This gets appv2.py
        mod_time = os.path.getmtime(app_file)
        last_updated = datetime.fromtimestamp(mod_time)
        
        return {
            'app_last_updated': last_updated,
            'app_version': '2.0 Enhanced'
        }
    except:
        # Fallback if file access fails
        return {
            'app_last_updated': datetime(2025, 1, 1),
            'app_version': '2.0 Enhanced'
        }

# Pagination helper class (from original code)
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

# ROUTES

@app.route('/')
def index():
    """Landing page with intro and evaluation count"""
    current_user = get_current_user()
    session_id = get_or_create_session()
    
    evaluation_count = get_user_evaluation_count()
    available_memes = get_available_memes_count()
    can_upload = can_user_upload()
    
    return render_template('index.html', 
                         evaluation_count=evaluation_count, 
                         available_memes=available_memes,
                         eval_mems = EVAL_COUNT,
                         memes_min = MIN_MEME_COUNT,
                         can_upload=can_upload,
                         development=DEVELOPMENT,
                         current_user=current_user)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration with automatic login"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        country = request.form.get('country', '').strip()
        affiliation = request.form.get('affiliation', '').strip()
        research_interest = request.form.get('research_interest', '').strip()
        
        # Notification preferences
        notify_updates = 'notify_updates' in request.form
        notify_milestones = 'notify_milestones' in request.form
        data_access = 'data_access' in request.form
        
        # Validation
        if not name or not email or not country:
            flash('Please fill in all required fields.')
            return redirect(request.url)
        
        if 'privacy_agreement' not in request.form:
            flash('Please agree to the privacy terms.')
            return redirect(request.url)
        
        # Check if email already exists
        conn = get_db_connection()
        existing_user = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        
        if existing_user:
            flash('An account with this email already exists. We\'ll send you a login link instead!')
            conn.close()
            # Send login link to existing user
            send_login_link(email)
            return redirect(url_for('login_sent', email=email))
        
        # Create new user
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users 
            (name, email, country, affiliation, research_interest, 
             notify_updates, notify_milestones, data_access_interest)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, email, country, affiliation, research_interest,
              notify_updates, notify_milestones, data_access))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Auto-login the user (since they just registered)
        session['user_id'] = user_id
        session['user_name'] = name
        session['user_email'] = email
        
        flash(f'Welcome to MemeQA, {name}! Your account has been created successfully.')
        return redirect(url_for('index'))
    
    return render_template('register.html',
                           eval_mems = EVAL_COUNT,
                           memes_min = MIN_MEME_COUNT)

@app.route('/request_login', methods=['POST'])
def request_login():
    """Request a login link via email"""
    email = request.form.get('login_email', '').strip().lower()
    
    if not email:
        flash('Please enter your email address.')
        return redirect(url_for('register'))
    
    # Check if user exists
    conn = get_db_connection()
    user = conn.execute('SELECT id, name FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    
    if not user:
        flash('No account found with that email. Please register first.')
        return redirect(url_for('register'))
    
    # Send login link
    send_login_link(email)
    return redirect(url_for('login_sent', email=email))

def send_login_link(email):
    """Send a login link to the user's email"""
    token = generate_login_token(email)
    login_url = url_for('login_with_token', token=token, email=email, _external=True)
    
    subject = "🎭 MemeQA Login Link"
    body = f"""
Hello!

Click the link below to log into your MemeQA account:

{login_url}

This link will expire in 24 hours.

If you didn't request this login, you can safely ignore this email.

Best regards,
The MemeQA Research Team
THWS & CAIRO
    """.strip()
    
    send_email(email, subject, body)

@app.route('/login_sent')
def login_sent():
    """Show confirmation that login link was sent"""
    email = request.args.get('email', '')
    return render_template('login_sent.html',eval_mems = EVAL_COUNT,
                           memes_min = MIN_MEME_COUNT,email=email)

@app.route('/login/<token>')
def login_with_token(token):
    """Login using email token"""
    email = request.args.get('email', '').lower()
    
    if not email or not verify_login_token(token, email):
        flash('Invalid or expired login link. Please request a new one.')
        return redirect(url_for('register'))
    
    # Find user
    conn = get_db_connection()
    user = conn.execute('SELECT id, name, email FROM users WHERE email = ?', (email,)).fetchone()
    
    if not user:
        flash('Account not found. Please register first.')
        conn.close()
        return redirect(url_for('register'))
    
    # Update last login
    conn.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
    conn.commit()
    conn.close()
    
    # Log in user
    session['user_id'] = user['id']
    session['user_name'] = user['name']
    session['user_email'] = user['email']
    
    flash(f'Welcome back, {user["name"]}!')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    flash('You have been logged out successfully.')
    return redirect(url_for('index'))

# Helper template for login_sent.html
def create_login_sent_template():
    """Template content for login_sent.html"""
    return '''<!-- templates/login_sent.html -->
{% extends "base.html" %}

{% block title %}Login Link Sent - MemeQA{% endblock %}

{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="text-center mb-4">
            <div class="display-1 text-success">📧</div>
            <h1>Check Your Email!</h1>
        </div>
        
        <div class="card shadow-sm">
            <div class="card-body text-center">
                <h5 class="card-title">Login Link Sent</h5>
                <p class="card-text">
                    We've sent a login link to:
                    <br><strong>{{ email }}</strong>
                </p>
                <p class="text-muted small">
                    Click the link in your email to log into your MemeQA account. 
                    The link will expire in 24 hours.
                </p>
                
                <hr>
                
                <div class="d-grid gap-2 d-md-block">
                    <a href="{{ url_for('index') }}" class="btn btn-primary">
                        <i class="bi bi-house"></i> Back to Home
                    </a>
                    <a href="{{ url_for('register') }}" class="btn btn-outline-secondary">
                        <i class="bi bi-arrow-left"></i> Back to Login
                    </a>
                </div>
            </div>
        </div>
        
        <div class="text-center mt-4">
            <small class="text-muted">
                Didn't receive the email? Check your spam folder or 
                <a href="{{ url_for('register') }}">request a new link</a>.
            </small>
        </div>
    </div>
</div>
{% endblock %}'''

# Updated profile route for app.py
@app.route('/profile')
def profile():
    """User profile page with safe data handling"""
    current_user = get_current_user()
    if not current_user:
        flash('Please register or log in to view your profile.')
        return redirect(url_for('register'))
    
    conn = get_db_connection()
    
    try:
        # Get user's recent memes with analytics
        recent_memes = conn.execute('''
            SELECT m.*, 
                   COALESCE(a.accuracy_rate, 0.0) as accuracy_rate, 
                   COALESCE(a.total_evaluations, 0) as total_evaluations
            FROM memes m
            LEFT JOIN meme_analytics a ON m.id = a.meme_id
            WHERE m.uploader_user_id = ?
            ORDER BY m.upload_date DESC
            LIMIT 10
        ''', (current_user['id'],)).fetchall()
        
        # Get evaluation statistics with safe defaults
        evaluation_stats_raw = conn.execute('''
            SELECT 
                COUNT(*) as total_evaluations,
                COUNT(CASE WHEN was_correct = 1 THEN 1 END) as correct_evaluations,
                AVG(CASE WHEN was_correct = 1 THEN 1.0 ELSE 0.0 END) as accuracy,
                AVG(evaluation_time_seconds) as avg_time
            FROM evaluations 
            WHERE user_id = ?
        ''', (current_user['id'],)).fetchone()
        
        # Create safe evaluation stats with defaults
        evaluation_stats = {
            'total_evaluations': evaluation_stats_raw['total_evaluations'] if evaluation_stats_raw else 0,
            'correct_evaluations': evaluation_stats_raw['correct_evaluations'] if evaluation_stats_raw else 0,
            'accuracy': evaluation_stats_raw['accuracy'] if evaluation_stats_raw and evaluation_stats_raw['accuracy'] else 0.0,
            'avg_time': evaluation_stats_raw['avg_time'] if evaluation_stats_raw and evaluation_stats_raw['avg_time'] else 0.0
        }
        
        # Get user's contribution rank (simplified)
        total_users = conn.execute('SELECT COUNT(*) as count FROM users WHERE total_submissions > 0').fetchone()
        user_rank_query = conn.execute('''
            SELECT COUNT(*) as rank FROM users 
            WHERE total_submissions > ? AND id != ?
        ''', (current_user['total_submissions'] or 0, current_user['id'])).fetchone()
        
        user_rank = (user_rank_query['rank'] + 1) if user_rank_query else 1
        total_contributors = total_users['count'] if total_users else 1
        
        # Calculate rank percentage
        if total_contributors > 0:
            rank_percentile = (user_rank / total_contributors) * 100
            if rank_percentile <= 10:
                contributor_rank = "Top 10%"
            elif rank_percentile <= 25:
                contributor_rank = "Top 25%"
            elif rank_percentile <= 50:
                contributor_rank = "Top Half"
            else:
                contributor_rank = "Contributing Member"
        else:
            contributor_rank = "Pioneer"
        
        # Calculate accuracy rate for display
        accuracy_rate = int(evaluation_stats['accuracy'] * 100) if evaluation_stats['accuracy'] else 0
        
    except Exception as e:
        print(f"Error in profile route: {e}")
        # Fallback to safe defaults
        recent_memes = []
        evaluation_stats = {
            'total_evaluations': 0,
            'correct_evaluations': 0,
            'accuracy': 0.0,
            'avg_time': 0.0
        }
        contributor_rank = "Member"
        accuracy_rate = 0
        
    finally:
        conn.close()
    
    return render_template('profile.html',
                         contributor=current_user,
                         recent_memes=recent_memes,
                         evaluation_stats=evaluation_stats,
                         contributor_rank=contributor_rank,
                         accuracy_rate=accuracy_rate,
                         eval_mems=EVAL_COUNT,
                         memes_min=MIN_MEME_COUNT)

@app.route('/gallery')
def gallery():
    """Display uploaded memes with enhanced pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 4, type=int)
    
    # Limit per_page options for security
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
    
    current_user = get_current_user()
    
    return render_template('gallery.html', 
                         memes=pagination,
                         per_page=per_page,
                         current_user=current_user,
                         eval_mems = EVAL_COUNT,
                         memes_min = MIN_MEME_COUNT)
# Updated evaluation table schema - add this to your migration
def add_evaluation_fields():
    """Add new fields for humor/emotion evaluation"""
    conn = sqlite3.connect('memes.db')
    cursor = conn.cursor()
    
    try:
        # Add new columns for humor/emotion evaluation
        new_eval_columns = [
            ('evaluated_humor_type', 'TEXT'),
            ('evaluated_emotions', 'TEXT'),  # JSON array
            ('evaluated_context_level', 'TEXT'),
            ('matches_humor_type', 'BOOLEAN'),
            ('emotion_overlap_score', 'REAL')  # 0.0-1.0 based on overlap
        ]
        
        for column_name, column_type in new_eval_columns:
            try:
                cursor.execute(f"ALTER TABLE evaluations ADD COLUMN {column_name} {column_type}")
                print(f"Added evaluation column: {column_name}")
            except sqlite3.OperationalError:
                pass  # Column already exists
        
        conn.commit()
        
    except Exception as e:
        print(f"Error adding evaluation fields: {e}")
        conn.rollback()
    finally:
        conn.close()

@app.route('/evaluate')
def evaluate():
    """Show humor/emotion evaluation page"""
    current_user = get_current_user()
    session_id = get_or_create_session()
    
    evaluation_count = get_user_evaluation_count()
    available_memes = get_available_memes_count()
    
    if evaluation_count >= EVAL_COUNT:
        flash('You have completed all required evaluations! You can now upload memes.')
        return redirect(url_for('upload_file'))
    
    if available_memes < MIN_MEME_COUNT:
        flash(f'Only {available_memes} memes available for evaluation. You can upload without completing 10 evaluations!')
        return redirect(url_for('upload_file'))
    
    meme = get_random_meme_for_evaluation()
    
    if not meme:
        flash('No more memes available for evaluation. You can now upload your own!')
        return redirect(url_for('upload_file'))
    
    return render_template('evaluate_enhanced.html', 
                         meme=meme, 
                         evaluation_count=evaluation_count,
                         current_user=current_user,
                         eval_mems = EVAL_COUNT,
                         memes_min=MIN_MEME_COUNT)

@app.route('/submit_humor_emotion_evaluation', methods=['POST'])
def submit_humor_emotion_evaluation():
    """Submit humor and emotion evaluation"""
    current_user = get_current_user()
    session_id = get_or_create_session()
    
    meme_id = request.form.get('meme_id')
    evaluated_humor_type = request.form.get('humor_type')
    evaluated_emotions = request.form.getlist('emotions')
    evaluated_context_level = request.form.get('context_level', '')
    evaluation_time = request.form.get('evaluation_time', 0, type=int)
    confidence_level = request.form.get('confidence_level', 3, type=int)
    
    if not meme_id or not evaluated_humor_type or not evaluated_emotions:
        flash('Please complete all required fields.')
        return redirect(url_for('evaluate'))
    
    # Get the meme to compare against
    conn = get_db_connection()
    meme = conn.execute('''
        SELECT humor_type, emotions_conveyed 
        FROM memes 
        WHERE id = ?
    ''', (meme_id,)).fetchone()
    
    if not meme:
        flash('Meme not found.')
        return redirect(url_for('evaluate'))
    
    # Calculate correctness scores
    try:
        # Check humor type match
        original_humor_type = meme['humor_type']
        matches_humor_type = (evaluated_humor_type == original_humor_type) if original_humor_type else None
        
        # Calculate emotion overlap
        if meme['emotions_conveyed']:
            try:
                original_emotions = json.loads(meme['emotions_conveyed'])
                if isinstance(original_emotions, list) and len(original_emotions) > 0:
                    # Calculate overlap score (intersection / union)
                    evaluated_set = set(evaluated_emotions)
                    original_set = set(original_emotions)
                    
                    if len(original_set) > 0:
                        intersection = len(evaluated_set.intersection(original_set))
                        union = len(evaluated_set.union(original_set))
                        emotion_overlap_score = intersection / union if union > 0 else 0.0
                    else:
                        emotion_overlap_score = 0.0
                else:
                    emotion_overlap_score = 0.0
            except (json.JSONDecodeError, TypeError):
                emotion_overlap_score = 0.0
        else:
            emotion_overlap_score = 0.0
        
        # Convert emotions to JSON
        emotions_json = json.dumps(evaluated_emotions)
        
        # Save evaluation
        conn.execute('''
            INSERT INTO evaluations 
            (session_id, user_id, meme_id, chosen_description, 
             evaluated_humor_type, evaluated_emotions, evaluated_context_level,
             matches_humor_type, emotion_overlap_score,
             confidence_level, evaluation_time_seconds) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_id, 
            current_user['id'] if current_user else None, 
            meme_id, 
            1,  # Default value for chosen_description (legacy field)
            evaluated_humor_type,
            emotions_json,
            evaluated_context_level,
            matches_humor_type,
            emotion_overlap_score,
            confidence_level, 
            evaluation_time
        ))
        
        # Update user stats if logged in
        if current_user:
            # Calculate new accuracy based on humor and emotion scores
            user_evals = conn.execute('''
                SELECT 
                    COUNT(*) as total,
                    AVG(CASE WHEN matches_humor_type THEN 1.0 ELSE 0.0 END) as humor_accuracy,
                    AVG(emotion_overlap_score) as emotion_accuracy
                FROM evaluations 
                WHERE user_id = ? AND matches_humor_type IS NOT NULL
            ''', (current_user['id'],)).fetchone()
            
            if user_evals['total'] > 0:
                # Combined accuracy: 50% humor accuracy + 50% emotion accuracy
                combined_accuracy = (
                    (user_evals['humor_accuracy'] or 0) * 0.5 + 
                    (user_evals['emotion_accuracy'] or 0) * 0.5
                )
                
                conn.execute('''
                    UPDATE users 
                    SET total_evaluations = ?, evaluation_accuracy = ?
                    WHERE id = ?
                ''', (user_evals['total'], combined_accuracy, current_user['id']))
        
        conn.commit()
        
        evaluation_count = get_user_evaluation_count()
        
        # Provide feedback
        feedback_parts = []
        
        if matches_humor_type is not None:
            if matches_humor_type:
                feedback_parts.append("✅ Humor type correct!")
            else:
                feedback_parts.append(f"📝 Humor: You said '{evaluated_humor_type}', original was '{original_humor_type}'")
        
        if emotion_overlap_score > 0:
            if emotion_overlap_score >= 0.7:
                feedback_parts.append("✅ Great emotion match!")
            elif emotion_overlap_score >= 0.3:
                feedback_parts.append("📝 Good emotion overlap!")
            else:
                feedback_parts.append("📝 Some emotion differences noted")
        
        feedback = " | ".join(feedback_parts) if feedback_parts else "Thanks for your evaluation!"
        flash(f'{feedback} Progress: {evaluation_count}/{EVAL_COUNT} evaluations completed.')
        
    except Exception as e:
        print(f"Error processing evaluation: {e}")
        flash('Error processing evaluation. Please try again.')
        conn.rollback()
    finally:
        conn.close()
    
    evaluation_count = get_user_evaluation_count()
    
    if evaluation_count >= 10:
        flash('🎉 Congratulations! You have completed all 10 evaluations. You can now upload your own meme!')
        return redirect(url_for('upload_file'))
    else:
        return redirect(url_for('evaluate'))

# Updated analytics for humor/emotion evaluation
@app.route('/evaluation_analytics')
def evaluation_analytics():
    """Analytics for humor/emotion evaluation performance"""
    if not DEVELOPMENT:
        abort(403)
    
    conn = get_db_connection()
    
    try:
        # Humor type accuracy
        humor_stats = conn.execute('''
            SELECT 
                evaluated_humor_type,
                COUNT(*) as total_evaluations,
                AVG(CASE WHEN matches_humor_type THEN 1.0 ELSE 0.0 END) as accuracy
            FROM evaluations 
            WHERE evaluated_humor_type IS NOT NULL AND matches_humor_type IS NOT NULL
            GROUP BY evaluated_humor_type
            ORDER BY total_evaluations DESC
        ''').fetchall()
        
        # Emotion overlap statistics
        emotion_stats = conn.execute('''
            SELECT 
                AVG(emotion_overlap_score) as avg_overlap,
                MIN(emotion_overlap_score) as min_overlap,
                MAX(emotion_overlap_score) as max_overlap,
                COUNT(*) as total_evaluations
            FROM evaluations 
            WHERE emotion_overlap_score IS NOT NULL
        ''').fetchone()
        
        # Most confused memes (low accuracy)
        difficult_memes = conn.execute('''
            SELECT 
                m.id, m.original_filename, m.humor_type, m.emotions_conveyed,
                AVG(CASE WHEN e.matches_humor_type THEN 1.0 ELSE 0.0 END) as humor_accuracy,
                AVG(e.emotion_overlap_score) as emotion_accuracy,
                COUNT(*) as evaluation_count
            FROM memes m
            JOIN evaluations e ON m.id = e.meme_id
            WHERE e.matches_humor_type IS NOT NULL
            GROUP BY m.id
            HAVING COUNT(*) >= 3
            ORDER BY (humor_accuracy + emotion_accuracy) ASC
            LIMIT 10
        ''').fetchall()
        
        # Best performing memes (high accuracy)
        easy_memes = conn.execute('''
            SELECT 
                m.id, m.original_filename, m.humor_type, m.emotions_conveyed,
                AVG(CASE WHEN e.matches_humor_type THEN 1.0 ELSE 0.0 END) as humor_accuracy,
                AVG(e.emotion_overlap_score) as emotion_accuracy,
                COUNT(*) as evaluation_count
            FROM memes m
            JOIN evaluations e ON m.id = e.meme_id
            WHERE e.matches_humor_type IS NOT NULL
            GROUP BY m.id
            HAVING COUNT(*) >= 3
            ORDER BY (humor_accuracy + emotion_accuracy) DESC
            LIMIT 10
        ''').fetchall()
        
    except Exception as e:
        print(f"Error in evaluation analytics: {e}")
        humor_stats = []
        emotion_stats = None
        difficult_memes = []
        easy_memes = []
    finally:
        conn.close()
    
    return render_template('evaluation_analytics.html',
                         humor_stats=humor_stats,
                         emotion_stats=emotion_stats,
                         difficult_memes=difficult_memes,
                         easy_memes=easy_memes)

# Helper function to get random meme that needs evaluation
def get_random_meme_for_evaluation():
    """Get a random meme that the user hasn't evaluated yet"""
    current_user = get_current_user()
    session_id = get_or_create_session()
    
    conn = get_db_connection()
    
    # Get memes that have the required fields and user hasn't evaluated
    if current_user:
        meme = conn.execute('''
            SELECT * FROM memes 
            WHERE humor_type IS NOT NULL 
            AND emotions_conveyed IS NOT NULL 
            AND id NOT IN (
                SELECT meme_id FROM evaluations WHERE user_id = ?
            ) 
            ORDER BY RANDOM() LIMIT 1
        ''', (current_user['id'],)).fetchone()
    else:
        meme = conn.execute('''
            SELECT * FROM memes 
            WHERE humor_type IS NOT NULL 
            AND emotions_conveyed IS NOT NULL 
            AND id NOT IN (
                SELECT meme_id FROM evaluations 
                WHERE session_id = ? AND (user_id IS NULL OR user_id = "")
            ) 
            ORDER BY RANDOM() LIMIT 1
        ''', (session_id,)).fetchone()
    
    conn.close()
    return meme

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """Simplified upload with conditional user info"""
    current_user = get_current_user()
    session_id = get_or_create_session()
    
    evaluation_count = get_user_evaluation_count()
    available_memes = get_available_memes_count()
    
    if not can_user_upload():
        remaining_evaluations = EVAL_COUNT - evaluation_count
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
            flash('Please select a valid image file (PNG, JPG, JPEG, or WebP).')
            return redirect(request.url)
        
        # Extract form data
        form_data = {
            # Contributor Information (only if not logged in)
            'contributor_name': request.form.get('contributor_name', '').strip() if not current_user else '',
            'contributor_email': request.form.get('contributor_email', '').strip() if not current_user else '',
            'contributor_country': request.form.get('contributor_country', '').strip() if not current_user else '',
            
            # Meme Information
            'meme_origin_country': request.form.get('meme_origin_country', '').strip(),
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
            
            # Meme Description (single description instead of 4)
            'meme_description': request.form.get('meme_description', '').strip(),
            
            # Additional Data
            'additional_notes': request.form.get('additional_notes', '').strip(),
            'terms_agreement': request.form.get('terms_agreement') == 'on'
        }
        
        # Validate required fields
        required_fields = [
            'platform_found', 'meme_content', 'estimated_year',
            'cultural_reach', 'humor_explanation', 'humor_type', 'context_required',
            'meme_description'
        ]
        
        # Add contributor country as required if not logged in
        if not current_user:
            required_fields.append('contributor_country')
        
        missing_fields = [field for field in required_fields if not form_data[field]]
        
        if missing_fields:
            flash(f'Please fill in all required fields: {", ".join(missing_fields)}')
            return redirect(request.url)
        
        # Validate emotions (at least one must be selected)
        if not form_data['emotions']:
            flash('Please select at least one emotion that the meme conveys.')
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
        
        # Convert emotions list to JSON
        emotions_json = json.dumps(form_data['emotions'])
        
        # Use current user data if available, otherwise form data
        if current_user:
            contributor_name = current_user['name']
            contributor_email = current_user['email']
            contributor_country = current_user['country']
            uploader_user_id = current_user['id']
        else:
            contributor_name = form_data['contributor_name']
            contributor_email = form_data['contributor_email']
            contributor_country = form_data['contributor_country']
            uploader_user_id = None
        
        # Save to database with new fields
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO memes (
                    filename, original_filename, contributor_name, contributor_email,
                    contributor_country, meme_origin_country, platform_found, 
                    uploader_session, uploader_user_id,
                    meme_content, meme_template, estimated_year, cultural_reach, niche_community,
                    humor_explanation, humor_type, emotions_conveyed,
                    cultural_references, context_required, age_group_target,
                    meme_description, additional_notes, terms_agreement
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                unique_filename, original_filename, contributor_name, contributor_email,
                contributor_country, form_data['meme_origin_country'], form_data['platform_found'], 
                session_id, uploader_user_id,
                form_data['meme_content'], form_data['meme_template'], form_data['estimated_year'], 
                form_data['cultural_reach'], form_data['niche_community'],
                form_data['humor_explanation'], form_data['humor_type'], emotions_json,
                form_data['cultural_references'], form_data['context_required'], form_data['age_group_target'],
                form_data['meme_description'], form_data['additional_notes'], form_data['terms_agreement']
            ))
            
            meme_id = cursor.lastrowid
            
            # Update user stats if logged in
            if current_user:
                cursor.execute('''
                    UPDATE users 
                    SET total_submissions = total_submissions + 1
                    WHERE id = ?
                ''', (current_user['id'],))
            
            conn.commit()
            flash('Meme uploaded and classified successfully! Thank you for your detailed contribution to our research.')
            
        except sqlite3.OperationalError as e:
            # Handle case where new columns don't exist yet
            if "no such column" in str(e):
                flash('Database needs to be updated. Please run the migration script first.')
                print(f"Database migration needed: {e}")
            else:
                flash('Error saving meme. Please try again.')
                print(f"Database error: {e}")
            conn.rollback()
            return redirect(request.url)
            
        finally:
            conn.close()
        
        return redirect(url_for('gallery'))
    
    return render_template('upload_simplified.html',
                           current_user=current_user,
                           eval_mems = EVAL_COUNT,
                           memes_min = MIN_MEME_COUNT)

@app.route('/submit_evaluation', methods=['POST'])
def submit_evaluation():
    """Enhanced evaluation submission with correctness tracking"""
    current_user = get_current_user()
    session_id = get_or_create_session()
    
    meme_id = request.form.get('meme_id')
    chosen_description = request.form.get('chosen_description')
    evaluation_time = request.form.get('evaluation_time', 0, type=int)  # Time in seconds
    confidence_level = request.form.get('confidence_level', 3, type=int)  # 1-4 confidence rating
    
    if not meme_id or not chosen_description:
        flash('Please select a description.')
        return redirect(url_for('evaluate'))
    
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
           (session_id, user_id, meme_id, chosen_description, was_correct, 
            confidence_level, evaluation_time_seconds) 
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (session_id, current_user['id'] if current_user else None, meme_id, 
         chosen_description, was_correct, confidence_level, evaluation_time)
    )
    
    # Update user stats if logged in
    if current_user:
        # Get updated stats
        stats = conn.execute('''
            SELECT COUNT(*) as total, COUNT(CASE WHEN was_correct THEN 1 END) as correct
            FROM evaluations WHERE user_id = ?
        ''', (current_user['id'],)).fetchone()
        
        accuracy = stats['correct'] / stats['total'] if stats['total'] > 0 else 0
        
        conn.execute('''
            UPDATE users 
            SET total_evaluations = ?, evaluation_accuracy = ?
            WHERE id = ?
        ''', (stats['total'], accuracy, current_user['id']))
    
    conn.commit()
    conn.close()
    
    # Update analytics
    update_meme_analytics(meme_id, was_correct, evaluation_time, confidence_level)
    
    evaluation_count = get_user_evaluation_count()
    
    # Provide feedback on correctness
    if was_correct:
        flash(f'✅ Correct! You identified the best description. Progress: {evaluation_count}/10')
    else:
        flash(f'❌ Not quite right, but thanks for participating! Progress: {evaluation_count}/10')
    
    if evaluation_count >= EVAL_COUNT:
        flash(f'🎉 Congratulations! You have completed all {EVAL_COUNT} evaluations. You can now upload your own meme!')
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
    registered_users = conn.execute('SELECT COUNT(*) as count FROM users WHERE is_active = 1').fetchone()['count']
    
    conn.close()
    
    current_user = get_current_user()
    
    return render_template('stats.html', 
                         total_memes=total_memes,
                         total_evaluations=total_evaluations,
                         unique_evaluators=unique_evaluators,
                         registered_users=registered_users,
                         current_user=current_user,
                         eval_mems = EVAL_COUNT,
                         memes_min = MIN_MEME_COUNT)

@app.route('/analytics')
def analytics():
    """Research analytics dashboard with proper None handling"""
    current_user = get_current_user()
    
    conn = get_db_connection()
    
    try:
        # Basic stats
        total_memes = conn.execute('SELECT COUNT(*) as count FROM memes').fetchone()['count']
        total_evaluations = conn.execute('SELECT COUNT(*) as count FROM evaluations').fetchone()['count']
        unique_evaluators = conn.execute('SELECT COUNT(DISTINCT session_id) as count FROM evaluations').fetchone()['count']
        
        # Try to get registered contributors, fallback if users table doesn't exist
        try:
            registered_contributors = conn.execute('SELECT COUNT(*) as count FROM users WHERE is_active = 1').fetchone()['count']
        except:
            registered_contributors = 0
        
        # Accuracy statistics with None handling
        accuracy_query = '''
            SELECT 
                AVG(CASE WHEN was_correct THEN 1.0 ELSE 0.0 END) as overall_accuracy,
                COUNT(CASE WHEN was_correct THEN 1 END) as correct_evaluations,
                COUNT(*) as total_evaluations
            FROM evaluations
            WHERE was_correct IS NOT NULL
        '''
        
        try:
            accuracy_stats_raw = conn.execute(accuracy_query).fetchone()
            
            # Create a safe accuracy_stats object
            if accuracy_stats_raw and accuracy_stats_raw['total_evaluations'] > 0:
                accuracy_stats = {
                    'overall_accuracy': accuracy_stats_raw['overall_accuracy'] or 0.0,
                    'correct_evaluations': accuracy_stats_raw['correct_evaluations'] or 0,
                    'total_evaluations': accuracy_stats_raw['total_evaluations'] or 0
                }
            else:
                accuracy_stats = {
                    'overall_accuracy': 0.0,
                    'correct_evaluations': 0,
                    'total_evaluations': 0
                }
        except Exception as e:
            print(f"Error getting accuracy stats: {e}")
            accuracy_stats = {
                'overall_accuracy': 0.0,
                'correct_evaluations': 0,
                'total_evaluations': 0
            }
        
        # Country distribution - handle missing columns gracefully
        try:
            country_stats = conn.execute('''
                SELECT country_of_submission, COUNT(*) as count 
                FROM memes 
                WHERE country_of_submission IS NOT NULL AND country_of_submission != ''
                GROUP BY country_of_submission 
                ORDER BY count DESC 
                LIMIT 10
            ''').fetchall()
        except:
            country_stats = []
        
        # Platform distribution
        try:
            platform_stats = conn.execute('''
                SELECT platform_found, COUNT(*) as count 
                FROM memes 
                WHERE platform_found IS NOT NULL AND platform_found != ''
                GROUP BY platform_found 
                ORDER BY count DESC
            ''').fetchall()
        except:
            platform_stats = []
        
        # Humor type distribution
        try:
            humor_stats = conn.execute('''
                SELECT humor_type, COUNT(*) as count 
                FROM memes 
                WHERE humor_type IS NOT NULL AND humor_type != ''
                GROUP BY humor_type 
                ORDER BY count DESC
            ''').fetchall()
        except:
            humor_stats = []
        
        # Cultural reach distribution
        try:
            cultural_stats = conn.execute('''
                SELECT cultural_reach, COUNT(*) as count 
                FROM memes 
                WHERE cultural_reach IS NOT NULL AND cultural_reach != ''
                GROUP BY cultural_reach 
                ORDER BY count DESC
            ''').fetchall()
        except:
            cultural_stats = []
        
        # Most difficult memes (lowest accuracy) - handle missing analytics table
        try:
            difficult_memes = conn.execute('''
                SELECT m.id, m.original_filename, 
                       COALESCE(m.meme_content, 'Legacy meme') as meme_content, 
                       COALESCE(a.accuracy_rate, 0.0) as accuracy_rate, 
                       COALESCE(a.total_evaluations, 0) as total_evaluations
                FROM memes m
                LEFT JOIN meme_analytics a ON m.id = a.meme_id
                WHERE COALESCE(a.total_evaluations, 0) >= 5
                ORDER BY COALESCE(a.accuracy_rate, 1.0) ASC
                LIMIT 10
            ''').fetchall()
        except:
            difficult_memes = []
        
        # Easiest memes (highest accuracy)
        try:
            easy_memes = conn.execute('''
                SELECT m.id, m.original_filename, 
                       COALESCE(m.meme_content, 'Legacy meme') as meme_content, 
                       COALESCE(a.accuracy_rate, 0.0) as accuracy_rate, 
                       COALESCE(a.total_evaluations, 0) as total_evaluations
                FROM memes m
                LEFT JOIN meme_analytics a ON m.id = a.meme_id
                WHERE COALESCE(a.total_evaluations, 0) >= 5
                ORDER BY COALESCE(a.accuracy_rate, 0.0) DESC
                LIMIT 10
            ''').fetchall()
        except:
            easy_memes = []
        
    except Exception as e:
        print(f"Error in analytics route: {e}")
        # Fallback values
        total_memes = 0
        total_evaluations = 0
        unique_evaluators = 0
        registered_contributors = 0
        accuracy_stats = {'overall_accuracy': 0.0, 'correct_evaluations': 0, 'total_evaluations': 0}
        country_stats = []
        platform_stats = []
        humor_stats = []
        cultural_stats = []
        difficult_memes = []
        easy_memes = []
    
    finally:
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
                         easy_memes=easy_memes,
                         current_user=current_user,
                         eval_mems = EVAL_COUNT,
                         memes_min = MIN_MEME_COUNT)

@app.route('/export_data')
def export_data():
    """Export research data (for researchers)"""
    if not DEVELOPMENT:  # Add proper authentication in production
        abort(403)
    
    conn = get_db_connection()
    
    # Get all meme data with analytics
    memes_data = conn.execute('''
        SELECT m.*, a.accuracy_rate, a.total_evaluations as analytics_evaluations,
               a.difficulty_score, a.avg_evaluation_time, a.avg_confidence_level
        FROM memes m
        LEFT JOIN meme_analytics a ON m.id = a.meme_id
        ORDER BY m.upload_date DESC
    ''').fetchall()
    
    # Get all evaluation data
    evaluations_data = conn.execute('''
        SELECT e.*, m.correct_description, m.cultural_reach, m.humor_type, m.estimated_year
        FROM evaluations e
        JOIN memes m ON e.meme_id = m.id
        ORDER BY e.evaluation_date DESC
    ''').fetchall()
    
    # Get user data (anonymized)
    users_data = conn.execute('''
        SELECT country, research_interest, total_submissions, total_evaluations, 
               evaluation_accuracy, registration_date
        FROM users 
        WHERE is_active = 1
        ORDER BY total_submissions DESC
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
        # Remove sensitive data
        meme_dict.pop('contributor_email', None)
        if not DEVELOPMENT:
            meme_dict.pop('contributor_name', None)
        memes_json.append(meme_dict)
    
    evaluations_json = [dict(eval) for eval in evaluations_data]
    users_json = [dict(user) for user in users_data]
    
    export_data = {
        'export_timestamp': datetime.now().isoformat(),
        'dataset_info': {
            'name': 'MemeQA',
            'version': '2.0',
            'description': 'Comprehensive meme understanding dataset with cultural and humor classifications',
            'institutions': ['THWS', 'CAIRO'],
            'license': 'Research Use Only'
        },
        'statistics': {
            'total_memes': len(memes_json),
            'total_evaluations': len(evaluations_json),
            'total_contributors': len(users_json)
        },
        'memes': memes_json,
        'evaluations': evaluations_json,
        'contributors': users_json
    }
    
    return jsonify(export_data)

@app.route('/reset_session')
def reset_session():
    """Reset current session (for testing)"""
    if not DEVELOPMENT:
        flash('This feature is only available in development mode.')
        return redirect(url_for('index'))
    
    session.clear()
    flash('Session reset! You can now start fresh.')
    return redirect(url_for('index'))

@app.route('/uploaded_file/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Helper functions

def get_user_evaluation_count():
    """Get number of evaluations completed by current session or user"""
    current_user = get_current_user()
    session_id = get_or_create_session()
    
    conn = get_db_connection()
    
    if current_user:
        count = conn.execute(
            'SELECT COUNT(*) as count FROM evaluations WHERE user_id = ?',
            (current_user['id'],)
        ).fetchone()['count']
    else:
        count = conn.execute(
            'SELECT COUNT(*) as count FROM evaluations WHERE session_id = ? AND user_id IS NULL',
            (session_id,)
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
    return evaluation_count >= EVAL_COUNT or available_memes < MIN_MEME_COUNT

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors - Page not found"""
    return render_template('404.html',
                           eval_mems = EVAL_COUNT,
                         memes_min = MIN_MEME_COUNT), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors - Internal server error"""
    return render_template('500.html',
                           eval_mems = EVAL_COUNT,
                         memes_min = MIN_MEME_COUNT), 500

@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 errors - Forbidden access"""
    return render_template('403.html',
                           eval_mems = EVAL_COUNT,
                         memes_min = MIN_MEME_COUNT), 403

@app.errorhandler(413)
def too_large_error(error):
    """Handle 413 errors - File too large"""
    return render_template('413.html',
                           eval_mems = EVAL_COUNT,
                         memes_min = MIN_MEME_COUNT), 413

# Template context processor to make current_user available in all templates
@app.context_processor
def inject_user():
    return dict(current_user=get_current_user())

if __name__ == '__main__':
    init_db()
    app.run(debug=DEVELOPMENT)