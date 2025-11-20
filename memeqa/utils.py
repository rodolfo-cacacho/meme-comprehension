# memeqa/utils.py

import os
import uuid
from werkzeug.utils import secure_filename
import secrets
import hashlib
import time
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import session, current_app
from memeqa.database import get_db
import json


def generate_login_token(email, secret_key):
    """Generate a secure login token for email"""
    timestamp = str(int(time.time()))
    random_part = secrets.token_urlsafe(32)
    token_data = f"{email}:{timestamp}:{random_part}"
    token_hash = hashlib.sha256(f"{token_data}:{secret_key}".encode()).hexdigest()
    final_token = base64.urlsafe_b64encode(f"{token_data}:{token_hash}".encode()).decode()
    return final_token

def verify_login_token(token, email, secret_key):
    """Verify a login token is valid"""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(':')
        
        if len(parts) != 4:
            return False
        
        token_email, timestamp, random_part, token_hash = parts
        
        if token_email != email:
            return False
        
        # Check token is not too old (24 hours)
        token_time = int(timestamp)
        if time.time() - token_time > 24 * 60 * 60:
            return False
        
        # Verify hash
        expected_hash = hashlib.sha256(f"{token_email}:{timestamp}:{random_part}:{secret_key}".encode()).hexdigest()
        return token_hash == expected_hash
        
    except Exception as e:
        print(f"Token verification error: {e}")
        return False

def send_email(to_email, subject, body, config):
    """Send email based on environment"""
    if config.get('DEVELOPMENT'):
        print("="*50)
        print(f"EMAIL TO: {to_email}")
        print(f"SUBJECT: {subject}")
        print(f"BODY:\n{body}")
        print("="*50)
        return True
    else:
        return send_email_gmail(to_email, subject, body, config)

def send_email_gmail(to_email, subject, body, config):
    """Send email via Gmail SMTP"""
    sender_email = config.get('GMAIL_USER')
    sender_password = config.get('GMAIL_APP_PASSWORD')
    
    if not sender_email or not sender_password:
        print("Gmail credentials not configured")
        return False
    
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

def get_current_user(db):
    """Get current user from session"""
    from flask import session
    if 'user_id' in session:
        user = db.execute('SELECT * FROM users WHERE id = ?', 
                         (session['user_id'],)).fetchone()
        return user
    return None

def get_upload_folder(app):
    """Get the absolute path to the upload folder"""
    import os
    upload_folder = app.config['UPLOAD_FOLDER']
    if not os.path.isabs(upload_folder):
        upload_folder = os.path.join(os.path.dirname(app.root_path), upload_folder)
    return upload_folder

def allowed_file(filename, allowed_extensions):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_uploaded_file(file, upload_folder):
    """Save uploaded file with unique filename"""
    original_filename = secure_filename(file.filename)
    unique_filename = str(uuid.uuid4()) + '_' + original_filename
    file_path = os.path.join(upload_folder, unique_filename)
    file.save(file_path)
    return unique_filename, original_filename

# Add to memeqa/utils.py

def get_session_stats(db, session_id, user_id=None):
    """Get upload and evaluation counts for current session/user"""
    if user_id:
        # For logged-in users, get their total stats
        user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        uploads = user['total_submissions'] if user else 0
        evaluations = user['total_evaluations'] if user else 0
    else:
        # For anonymous users, count from this session
        uploads = db.execute(
            'SELECT COUNT(*) as count FROM memes WHERE session_id = ? AND user_id IS NULL',
            (session_id,)
        ).fetchone()['count']
        
        evaluations = db.execute(
            'SELECT COUNT(*) as count FROM evaluations WHERE session_id = ? AND user_id IS NULL',
            (session_id,)
        ).fetchone()['count']
    
    return uploads, evaluations

def check_anonymous_limits(db, session_id):
    """Check if anonymous user has reached limits"""
    uploads, evaluations = get_session_stats(db, session_id)
    can_upload = uploads < 1  # Anonymous users can upload 1 meme
    can_evaluate = evaluations < 5  # Anonymous users can evaluate 5 memes
    return can_upload, can_evaluate, uploads, evaluations

def transfer_anonymous_data(db, session_id, user_id):
    """Transfer anonymous session data to registered user"""
    # Update memes uploaded in this session
    db.execute(
        'UPDATE memes SET user_id = ? WHERE session_id = ? AND user_id IS NULL',
        (user_id, session_id)
    )
    
    # Update evaluations from this session
    db.execute(
        'UPDATE evaluations SET user_id = ? WHERE session_id = ? AND user_id IS NULL',
        (user_id, session_id)
    )
    
    # Update user's total counts
    meme_count = db.execute(
        'SELECT COUNT(*) as count FROM memes WHERE user_id = ?',
        (user_id,)
    ).fetchone()['count']
    
    eval_count = db.execute(
        'SELECT COUNT(*) as count FROM evaluations WHERE user_id = ?',
        (user_id,)
    ).fetchone()['count']
    
    db.execute(
        'UPDATE users SET total_submissions = ?, total_evaluations = ? WHERE id = ?',
        (meme_count, eval_count, user_id)
    )
    
    db.commit()

def get_user_own_meme_ids(db, user_id):
    """Get IDs of memes uploaded by the user"""
    memes = db.execute(
        'SELECT id FROM memes WHERE user_id = ?',
        (user_id,)
    ).fetchall()
    return [m['id'] for m in memes]

def should_prompt_upload(evaluations_count):
    """Check if user should be prompted to upload (every 10 evaluations)"""
    return evaluations_count > 0 and evaluations_count % 10 == 0

def should_prompt_evaluate(uploads_count):
    """Check if user should be prompted to evaluate (every 5 uploads)"""
    return uploads_count > 0 and uploads_count % 5 == 0

def list_to_string(items):
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " or " + items[-1]

def parse_json_columns(memes, json_columns):
    """
    Parse JSON string columns in meme objects.
    
    Args:
        memes: Single meme object/row or list of meme objects/rows
        json_columns: List of column names that contain JSON strings
    """
    # Handle single meme case
    is_single = not isinstance(memes, list)
    meme_list = [memes] if is_single else memes
    
    parsed_memes = []
    for meme in meme_list:
        # Convert Row to dict
        meme_dict = dict(meme)
        
        # Parse JSON columns
        for column in json_columns:
            column_value = meme_dict.get(column)
            if column_value:
                try:
                    parsed = json.loads(column_value)
                    meme_dict[f'{column}_list'] = parsed if isinstance(parsed, list) else []
                except (json.JSONDecodeError, TypeError, ValueError):
                    meme_dict[f'{column}_list'] = []
            else:
                meme_dict[f'{column}_list'] = []
        
        parsed_memes.append(meme_dict)
    
    # Return single dict if input was single meme, otherwise return list
    return parsed_memes[0] if is_single else parsed_memes

class AppSession:
    def __init__(self, current_user=None):
        self.db = get_db()
        self.current_user = current_user
        self.session_id = session.get('session_id', str(uuid.uuid4()))
        session['session_id'] = self.session_id  # Persist
        self.user_id = current_user['id'] if current_user else None
        self.name = current_user['name'] if current_user else 'Anonymous'
        self._load_stats()

    def _load_stats(self):
        if self.current_user:
            user = self.db.execute('SELECT total_submissions, total_evaluations, evaluation_accuracy FROM users WHERE id = ?', (self.user_id,)).fetchone()
            self.upload_count = user['total_submissions'] if user else 0
            self.eval_count = user['total_evaluations'] if user else 0
            self.evaluation_accuracy = user['evaluation_accuracy'] if user else 0.0
            self.max_upload = current_app.config['REG_MAX_UPLOAD']
            self.max_eval = current_app.config['REG_MAX_EVAL']
        else:
            self.upload_count = self.db.execute('SELECT COUNT(*) as count FROM memes WHERE session_id = ? AND user_id IS NULL', (self.session_id,)).fetchone()['count'] or 0
            self.eval_count = self.db.execute('SELECT COUNT(*) as count FROM evaluations WHERE session_id = ? AND user_id IS NULL', (self.session_id,)).fetchone()['count'] or 0
            self.evaluation_accuracy = None  # Anon users don't have accuracy
            self.max_upload = current_app.config['ANON_MAX_UPLOAD']
            self.max_eval = current_app.config['ANON_MAX_EVAL']

    def check_limits(self):
        if self.current_user:
            return {'can_upload': True, 'can_evaluate': True, 'reason': None}  # Unlimited
        can_upload = self.upload_count < self.max_upload
        can_evaluate = self.eval_count < self.max_eval
        reason = 'Upload limit reached' if not can_upload else 'Evaluation limit reached' if not can_evaluate else None
        return {'can_upload': can_upload, 'can_evaluate': can_evaluate, 'reason': reason}

    def get_own_meme_ids(self):
        if self.current_user:
            memes = self.db.execute('SELECT id FROM memes WHERE user_id = ?', (self.user_id,)).fetchall()
        else:
            memes = self.db.execute('SELECT id FROM memes WHERE session_id = ? AND user_id IS NULL', (self.session_id,)).fetchall()
        return set(m['id'] for m in memes)

    def increment_upload(self):
        if self.current_user:
            self.db.execute('UPDATE users SET total_submissions = total_submissions + 1 WHERE id = ?', (self.user_id,))
            self.db.commit()
        self._load_stats()  # Refresh counts

    def increment_evaluation(self):
        if self.current_user:
            self.db.execute('UPDATE users SET total_evaluations = total_evaluations + 1 WHERE id = ?', (self.user_id,))
            self.db.commit()
        self._load_stats()

    def get_total_memes(self):
        result = self.db.execute('SELECT COUNT(*) as count FROM memes').fetchone()
        return result['count'] if result else 0

    def get_available_memes(self):
        own_meme_ids = self.get_own_meme_ids()
        if not own_meme_ids:
            result = self.db.execute('SELECT COUNT(*) as count FROM memes').fetchone()
        else:
            result = self.db.execute(
                'SELECT COUNT(*) as count FROM memes WHERE id NOT IN ({})'.format(','.join('?' * len(own_meme_ids))),
                tuple(own_meme_ids)
            ).fetchone()
        return result['count'] if result else 0


class Pagination:
    def __init__(self, page, per_page, total_count):
        self.page = page
        self.per_page = per_page
        self.total_count = total_count
        self._items = []
    
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