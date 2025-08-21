# memeqa/routes/memes.py
from flask import Blueprint, render_template, request, abort, send_from_directory, current_app, flash, redirect, url_for, session
from memeqa.database import get_db
from memeqa.utils import Pagination,allowed_file, save_uploaded_file, get_upload_folder,get_current_user
import json


def get_or_create_session():
    """Get or create session for tracking"""
    import uuid
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

def get_current_user(db):
    """Get current user from utils"""
    from memeqa.utils import get_current_user as get_user
    return get_user(db)

bp = Blueprint('memes', __name__)

@bp.route('/gallery')
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
    
    # Get database connection
    db = get_db()
    
    # Get total count for pagination
    total_count = db.execute('SELECT COUNT(*) as count FROM memes').fetchone()['count']
    
    # Check if page is out of range
    max_page = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    if page > max_page and total_count > 0:
        abort(404)
    
    # Get memes for current page
    memes = db.execute(
        'SELECT * FROM memes ORDER BY upload_date DESC LIMIT ? OFFSET ?',
        (per_page, offset)
    ).fetchall()
    
    # Create pagination object
    pagination = Pagination(page, per_page, total_count)
    pagination.items = memes
    
    # Don't need to pass current_user or config values - they're injected automatically!
    return render_template('memes/gallery.html', 
                         memes=pagination,
                         per_page=per_page)

# Add this route to memes.py
@bp.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """Handle meme upload with limits and proper form handling"""
    from memeqa.utils import check_anonymous_limits, should_prompt_evaluate, save_uploaded_file, allowed_file, get_upload_folder
    from werkzeug.utils import secure_filename
    import json
    import uuid
    
    db = get_db()
    current_user = get_current_user(db)
    session_id = get_or_create_session()
    
    # Check limits for anonymous users
    if not current_user:
        can_upload, can_evaluate, uploads, evaluations = check_anonymous_limits(db, session_id)
        if not can_upload:
            flash('You\'ve already uploaded a meme. Please register or log in to upload more!')
            return redirect(url_for('auth.register'))
    else:
        # Check if registered user should be prompted to evaluate
        if should_prompt_evaluate(current_user['total_submissions']):
            flash('🌟 Awesome! You\'ve uploaded 5 memes. Help evaluate other memes too!')
    
    if request.method == 'POST':
        # Check if file was uploaded
        if 'file' not in request.files:
            flash('No file selected')
            return redirect(request.url)
        
        file = request.files['file']
        
        # Check if file is valid
        allowed_extensions = current_app.config['ALLOWED_EXTENSIONS']
        if file.filename == '' or not allowed_file(file.filename, allowed_extensions):
            flash('Please select a valid image file (PNG, JPG, JPEG, or WebP).')
            return redirect(request.url)
        
        # Extract form data
        form_data = {
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
            
            # # Meme Description
            # 'meme_description': request.form.get('meme_description', '').strip(),
            
            # Additional Data
            'additional_notes': request.form.get('additional_notes', '').strip(),
            'terms_agreement': request.form.get('terms_agreement') == 'on'
        }
        
        # For anonymous users, get contributor info from form
        if not current_user:
            form_data['contributor_name'] = request.form.get('contributor_name', '').strip()
            form_data['contributor_email'] = request.form.get('contributor_email', '').strip()
            form_data['contributor_country'] = request.form.get('country_of_submission', '').strip()
        
        # Validate required fields
        required_fields = [
            'platform_found', 'meme_content', 'estimated_year',
            'cultural_reach', 'humor_explanation', 'humor_type', 'context_required',
            # 'meme_description'
        ]
        
        # Add contributor country as required if not logged in
        if not current_user:
            required_fields.append('contributor_country')
        
        missing_fields = [field for field in required_fields if not form_data.get(field)]
        
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
        upload_folder = get_upload_folder(current_app)
        filename, original_filename = save_uploaded_file(file, upload_folder)
        
        # Convert emotions list to JSON
        emotions_json = json.dumps(form_data['emotions'])
        
        # Use current user data if available, otherwise form data
        if current_user:
            contributor_name = current_user['name']
            contributor_email = current_user['email']
            contributor_country = current_user['country']
            uploader_user_id = current_user['id']
        else:
            contributor_name = form_data.get('contributor_name', '')
            contributor_email = form_data.get('contributor_email', '')
            contributor_country = form_data.get('contributor_country', '')
            uploader_user_id = None
        
        # Save to database
        cursor = db.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO memes (
                    filename, original_filename, contributor_name, contributor_email,
                    contributor_country, meme_origin_country, platform_found, 
                    uploader_session, uploader_user_id,
                    meme_content, meme_template, estimated_year, cultural_reach, niche_community,
                    humor_explanation, humor_type, emotions_conveyed,
                    cultural_references, context_required, age_group_target,
                    additional_notes, terms_agreement
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                filename, original_filename, contributor_name, contributor_email,
                contributor_country, form_data['meme_origin_country'], form_data['platform_found'], 
                session_id, uploader_user_id,
                form_data['meme_content'], form_data['meme_template'], form_data['estimated_year'], 
                form_data['cultural_reach'], form_data['niche_community'],
                form_data['humor_explanation'], form_data['humor_type'], emotions_json,
                form_data['cultural_references'], form_data['context_required'], form_data['age_group_target'],
                form_data['additional_notes'], form_data['terms_agreement']
            ))
            
            meme_id = cursor.lastrowid
            
            # Update user stats if logged in
            if current_user:
                cursor.execute('''
                    UPDATE users 
                    SET total_submissions = total_submissions + 1
                    WHERE id = ?
                ''', (current_user['id'],))
            
            db.commit()
            flash('Meme uploaded and classified successfully! Thank you for your detailed contribution to our research.')
            
            # Check if we should prompt for evaluation
            if current_user:
                total_uploads = current_user['total_submissions'] + 1
                if should_prompt_evaluate(total_uploads):
                    flash('🎯 You\'ve uploaded 5 memes! Now help evaluate others to improve the dataset!')
            
        except Exception as e:
            print(f"Database error: {e}")
            flash('Error saving meme. Please try again.')
            db.rollback()
            return redirect(request.url)
        
        return redirect(url_for('memes.gallery'))
    
    # GET request - show upload form
    # Pass current_user so template can conditionally show/hide fields
    return render_template('memes/upload.html', current_user=current_user)


@bp.route('/uploaded_file/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    upload_folder = get_upload_folder(current_app)
    return send_from_directory(upload_folder, filename)