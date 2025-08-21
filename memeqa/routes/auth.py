# memeqa/routes/auth.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, current_app
from memeqa.database import get_db
from memeqa.utils import get_current_user, generate_login_token, verify_login_token, send_email

bp = Blueprint('auth', __name__)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration with email confirmation"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        country = request.form.get('country', '').strip()
        affiliation = request.form.get('affiliation', '').strip()
        research_interest = request.form.get('research_interest', '').strip()
        
        # Notification preferences
        notify_updates = 1 if 'notify_updates' in request.form else 0
        notify_milestones = 1 if 'notify_milestones' in request.form else 0
        data_access = 1 if 'data_access' in request.form else 0
        
        # Validation
        if not name or not email or not country:
            flash('Please fill in all required fields.')
            return redirect(request.url)
        
        if 'privacy_agreement' not in request.form:
            flash('Please agree to the privacy terms.')
            return redirect(request.url)
        
        # Check if email already exists
        db = get_db()
        existing_user = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        
        if existing_user:
            flash('An account with this email already exists. We\'ll send you a login link instead!')
            send_login_link(email)
            return redirect(url_for('auth.login_sent', email=email))
        
        # Create new user (but NOT logged in yet)
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO users 
            (name, email, country, affiliation, research_interest, 
             notify_updates, notify_milestones, data_access_interest,
             total_submissions, total_evaluations, evaluation_accuracy, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0.0, 1)
        ''', (name, email, country, affiliation, research_interest,
              notify_updates, notify_milestones, data_access))
        
        db.commit()
        
        # Send confirmation email
        send_confirmation_email(name, email)
        
        flash(f'Welcome to MemeQA, {name}! Please check your email to confirm your account.')
        return redirect(url_for('auth.registration_sent', email=email))
    
    # GET request - show registration form
    return render_template('auth/register.html')

@bp.route('/registration_sent')
def registration_sent():
    """Show confirmation that registration email was sent"""
    email = request.args.get('email', '')
    return render_template('auth/registration_sent.html', email=email)

@bp.route('/request_login', methods=['POST'])
def request_login():
    """Request a login link via email"""
    email = request.form.get('login_email', '').strip().lower()
    
    if not email:
        flash('Please enter your email address.')
        return redirect(url_for('auth.register'))
    
    # Check if user exists
    db = get_db()
    user = db.execute('SELECT id, name FROM users WHERE email = ?', (email,)).fetchone()
    
    if not user:
        flash('No account found with that email. Please register first.')
        return redirect(url_for('auth.register'))
    
    # Send login link
    send_login_link(email)
    return redirect(url_for('auth.login_sent', email=email))

@bp.route('/login_sent')
def login_sent():
    """Show confirmation that login link was sent"""
    email = request.args.get('email', '')
    return render_template('auth/login_sent.html', email=email)

@bp.route('/login/<token>')
def login_with_token(token):
    """Login using email token"""
    email = request.args.get('email', '').lower()
    
    if not email or not verify_login_token(token, email, current_app.config['SECRET_KEY']):
        flash('Invalid or expired login link. Please request a new one.')
        return redirect(url_for('auth.register'))
    
    # Find user
    db = get_db()
    user = db.execute('SELECT id, name, email FROM users WHERE email = ?', (email,)).fetchone()
    
    if not user:
        flash('Account not found. Please register first.')
        return redirect(url_for('auth.register'))
    
    # Transfer anonymous data before logging in
    session_id = session.get('session_id')
    if session_id:
        from memeqa.utils import transfer_anonymous_data
        transfer_anonymous_data(db, session_id, user['id'])
        flash('Your anonymous contributions have been added to your account!')
    
    # Update last login
    db.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
    db.commit()
    
    # Log in user
    session['user_id'] = user['id']
    session['user_name'] = user['name']
    session['user_email'] = user['email']
    
    flash(f'Welcome back, {user["name"]}!')
    return redirect(url_for('main.index'))

@bp.route('/logout')
def logout():
    """User logout"""
    session.clear()
    flash('You have been logged out successfully.')
    return redirect(url_for('main.index'))

# In memeqa/routes/auth.py
@bp.route('/profile')
def profile():
    """User profile page with safe data handling"""
    db = get_db()
    current_user = get_current_user(db)
    
    if not current_user:
        flash('Please register or log in to view your profile.')
        return redirect(url_for('auth.register'))
    
    try:
        # Get user's recent memes with analytics
        recent_memes = db.execute('''
            SELECT m.*, 
                   COALESCE(a.accuracy_rate, 0.0) as accuracy_rate, 
                   COALESCE(a.total_evaluations, 0) as total_evaluations
            FROM memes m
            LEFT JOIN meme_analytics a ON m.id = a.meme_id
            WHERE m.uploader_user_id = ?
            ORDER BY m.upload_date DESC
            LIMIT 10
        ''', (current_user['id'],)).fetchall()
        
        # Get evaluation statistics
        evaluation_stats_raw = db.execute('''
            SELECT 
                COUNT(*) as total_evaluations,
                COUNT(CASE WHEN was_correct = 1 THEN 1 END) as correct_evaluations,
                AVG(CASE WHEN was_correct = 1 THEN 1.0 ELSE 0.0 END) as accuracy,
                AVG(evaluation_time_seconds) as avg_time
            FROM evaluations 
            WHERE user_id = ?
        ''', (current_user['id'],)).fetchone()
        
        # Create safe evaluation stats
        evaluation_stats = {
            'total_evaluations': evaluation_stats_raw['total_evaluations'] if evaluation_stats_raw else 0,
            'correct_evaluations': evaluation_stats_raw['correct_evaluations'] if evaluation_stats_raw else 0,
            'accuracy': evaluation_stats_raw['accuracy'] if evaluation_stats_raw and evaluation_stats_raw['accuracy'] else 0.0,
            'avg_time': evaluation_stats_raw['avg_time'] if evaluation_stats_raw and evaluation_stats_raw['avg_time'] else 0.0
        }
        
        # Get user's contribution rank
        total_users = db.execute('SELECT COUNT(*) as count FROM users WHERE total_submissions > 0').fetchone()
        
        # Use bracket notation instead of .get()
        user_submissions = current_user['total_submissions'] if current_user['total_submissions'] else 0
        
        user_rank_query = db.execute('''
            SELECT COUNT(*) as rank FROM users 
            WHERE total_submissions > ? AND id != ?
        ''', (user_submissions, current_user['id'])).fetchone()
        
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
        
        # Calculate accuracy rate
        accuracy_rate = int(evaluation_stats['accuracy'] * 100) if evaluation_stats['accuracy'] else 0
        
        # Get total evaluations for the user
        total_evals = current_user['total_evaluations'] if current_user['total_evaluations'] else 0
        
    except Exception as e:
        print(f"Error in profile route: {e}")
        import traceback
        traceback.print_exc()
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
        total_evals = 0
    
    return render_template('auth/profile.html',
                         contributor=current_user,
                         recent_memes=recent_memes,
                         evaluation_stats=evaluation_stats,
                         contributor_rank=contributor_rank,
                         accuracy_rate=accuracy_rate,
                         total_evals=total_evals)

# Helper functions
def send_login_link(email):
    """Send a login link to the user's email"""
    token = generate_login_token(email, current_app.config['SECRET_KEY'])
    login_url = url_for('auth.login_with_token', token=token, email=email, _external=True)
    
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
    
    send_email(email, subject, body, current_app.config)

def send_confirmation_email(name, email):
    """Send registration confirmation email"""
    token = generate_login_token(email, current_app.config['SECRET_KEY'])
    confirm_url = url_for('auth.login_with_token', token=token, email=email, _external=True)
    
    subject = "🎉 Welcome to MemeQA - Confirm Your Email"
    body = f"""
Hello {name}!

Welcome to MemeQA - the collaborative meme understanding research platform!

Please confirm your email address by clicking the link below:

{confirm_url}

This link will expire in 24 hours.

Once confirmed, you'll be able to:
- Evaluate memes to help train AI models
- Upload and classify your own memes
- Track your contributions and accuracy
- Help advance cross-cultural humor research

Best regards,
The MemeQA Research Team
THWS & CAIRO
    """.strip()
    
    send_email(email, subject, body, current_app.config)