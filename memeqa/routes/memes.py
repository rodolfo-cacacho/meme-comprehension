# memeqa/routes/memes.py
from flask import Blueprint, render_template, request, abort, send_from_directory, current_app, flash, redirect, url_for, session
from memeqa.database import get_db
# from memeqa.utils import Pagination,allowed_file, save_uploaded_file, get_upload_folder,get_current_user
from memeqa.utils import Pagination, allowed_file, get_upload_folder, get_current_user, AppSession,save_uploaded_file,list_to_string
import json


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


@bp.route('/upload', methods=['GET', 'POST'])
def upload_file():
    """Handle meme upload with improved validation and UX"""
    app_session = AppSession(get_current_user(get_db()))
    config = current_app.config
    limits = app_session.check_limits()

    # Check limits for anonymous users
    if not app_session.current_user and not limits['can_upload']:
        flash('You\'ve reached the limit of {} uploads. Please register or log in to upload more!'.format(config['ANON_MAX_UPLOAD']))
        return redirect(url_for('auth.register'))

    # Check if registered user should be prompted to evaluate
    if app_session.current_user and app_session.upload_count % config['PROMPT_EVAL_EVERY'] == 0:
        flash('🎉 Great job! You\'ve uploaded {} memes. Consider evaluating some more!'.format(config['PROMPT_EVAL_EVERY']))

    if request.method == 'POST':
        # Initialize form_data for template rendering
        form_data = {}
        
        try:
            # Check if file was uploaded
            if 'file' not in request.files:
                flash('No file selected', 'error')
                return render_template('memes/upload.html', 
                                     current_user=app_session.current_user, 
                                     form_data=form_data)
            
            file = request.files['file']
            
            # Check if file is valid
            allowed_extensions = config['ALLOWED_EXTENSIONS']
            if file.filename == '' or not allowed_file(file.filename, allowed_extensions):
                flash(f'Please select a valid image file ({list_to_string(allowed_extensions)}).', 'error')
                return render_template('memes/upload.html', 
                                     current_user=app_session.current_user, 
                                     form_data=form_data)
            
            # Check file size (16MB limit)
            file.seek(0, 2)  # Seek to end
            file_size = file.tell()
            file.seek(0)     # Reset to beginning
            
            if file_size > 16 * 1024 * 1024:  # 16MB
                flash('File size must be less than 16MB.', 'error')
                return render_template('memes/upload.html', 
                                     current_user=app_session.current_user, 
                                     form_data=form_data)
            
            # Extract and clean form data
            form_data = extract_and_validate_form_data(request.form)
            
            # Server-side validation (as backup to client-side)
            validation_errors = validate_form_data(form_data, app_session.current_user)
            
            if validation_errors:
                for error in validation_errors:
                    flash(error, 'error')
                return render_template('memes/upload.html', 
                                     current_user=app_session.current_user, 
                                     form_data=form_data)
            
            # Process and save file
            upload_folder = get_upload_folder(current_app)
            filename, original_filename = save_uploaded_file(file, upload_folder)
            
            # Convert emotions list to JSON
            emotions_json = json.dumps(form_data['emotions'])
            
            # Use current user data if available, otherwise form data
            if app_session.current_user:
                contributor_name = app_session.name
                contributor_email = app_session.current_user['email']
                contributor_country = app_session.current_user['country']
                uploader_user_id = app_session.user_id
            else:
                contributor_name = form_data.get('contributor_name', '')
                contributor_email = form_data.get('contributor_email', '')
                contributor_country = form_data.get('contributor_country', '')
                uploader_user_id = None
            
            # Save to database
            cursor = get_db().cursor()
            
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
                contributor_country, form_data.get('meme_origin_country', ''), 
                form_data['platform_found'], app_session.session_id, uploader_user_id,
                form_data['meme_content'], form_data.get('meme_template', ''), 
                form_data['estimated_year'], form_data['cultural_reach'], 
                form_data.get('niche_community', ''), form_data['humor_explanation'], 
                form_data['humor_type'], emotions_json, 
                form_data.get('cultural_references', ''), form_data['context_required'], 
                form_data.get('age_group_target', ''), form_data.get('additional_notes', ''), 
                form_data['terms_agreement']
            ))
            
            meme_id = cursor.lastrowid
            
            # Update user stats if logged in
            if app_session.current_user:
                app_session.increment_upload()
            
            get_db().commit()
            
            flash('Meme uploaded and classified successfully! Thank you for your detailed contribution to our research.', 'success')
            
            # Check if we should prompt for evaluation
            if app_session.current_user and app_session.upload_count % config['PROMPT_EVAL_EVERY'] == 0:
                flash('🎯 You\'ve uploaded {} memes! Now help evaluate others to improve the dataset!'.format(config['PROMPT_EVAL_EVERY']), 'info')
            
            return redirect(url_for('memes.gallery'))
            
        except Exception as e:
            current_app.logger.error(f"Upload error: {e}")
            get_db().rollback()
            flash('An error occurred while uploading. Please try again.', 'error')
            return render_template('memes/upload.html', 
                                 current_user=app_session.current_user, 
                                 form_data=form_data)
    
    # GET request - show upload form
    return render_template('memes/upload.html', current_user=app_session.current_user)


def extract_and_validate_form_data(form):
    """Extract and clean form data"""
    return {
        # Meme Information
        'meme_origin_country': form.get('meme_origin_country', '').strip(),
        'platform_found': form.get('platform_found', '').strip(),
        
        # Content Classification
        'meme_content': form.get('meme_content', '').strip(),
        'meme_template': form.get('meme_template', '').strip(),
        'estimated_year': form.get('estimated_year', '').strip(),
        'cultural_reach': form.get('cultural_reach', '').strip(),
        'niche_community': form.get('niche_community', '').strip(),
        
        # Humor & Emotional Analysis
        'humor_explanation': form.get('humor_explanation', '').strip(),
        'humor_type': form.get('humor_type', '').strip(),
        'emotions': form.getlist('emotions[]'),
        
        # Context & References
        'cultural_references': form.get('cultural_references', '').strip(),
        'context_required': form.get('context_required', '').strip(),
        'age_group_target': form.get('age_group_target', '').strip(),
        
        # Additional
        'additional_notes': form.get('additional_notes', '').strip(),
        'terms_agreement': form.get('terms_agreement') == 'on',
        
        # Contributor info (for anon users)
        'contributor_name': form.get('contributor_name', '').strip(),
        'contributor_email': form.get('contributor_email', '').strip(),
        'contributor_country': form.get('contributor_country', '').strip()
    }


def validate_form_data(form_data, current_user):
    """Validate form data and return list of errors"""
    errors = []
    
    # Required fields validation
    required_fields = [
        ('meme_content', 'Content description'),
        ('meme_origin_country', 'Meme origin country'),
        ('estimated_year', 'Estimated year'),
        ('cultural_reach', 'Cultural reach'),
        ('humor_explanation', 'Humor explanation'),
        ('humor_type', 'Humor type'),
        ('context_required', 'Context required'),
        ('platform_found', 'Platform where found'),
    ]
    
    for field, display_name in required_fields:
        if not form_data.get(field):
            errors.append(f'{display_name} is required')
    
    # Anonymous user specific validation
    if not current_user:
        if not form_data.get('contributor_country'):
            errors.append('Country is required')
    
    # Emotions validation
    if not form_data.get('emotions') or len(form_data['emotions']) == 0:
        errors.append('Please select at least one emotion')
    
    # Terms agreement validation
    if not form_data.get('terms_agreement'):
        errors.append('You must agree to the terms to upload')
    
    # Niche community validation
    if form_data.get('cultural_reach') == 'Niche Community' and not form_data.get('niche_community'):
        errors.append('Please specify the niche community when selecting "Niche Community" for cultural reach')
    
    # Email validation (if provided)
    if form_data.get('contributor_email') and '@' not in form_data['contributor_email']:
        errors.append('Please provide a valid email address')
    
    return errors


@bp.route('/uploaded_file/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    upload_folder = get_upload_folder(current_app)
    return send_from_directory(upload_folder, filename)