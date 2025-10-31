# memeqa/routes/memes.py
from flask import Blueprint, render_template, request, abort, send_from_directory, current_app, flash, redirect, url_for, session
from memeqa.database import get_db
from memeqa.utils import Pagination, allowed_file, get_upload_folder, get_current_user, AppSession, save_uploaded_file, list_to_string
import json
import datetime

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
    if app_session.current_user and app_session.upload_count % config['PROMPT_EVAL_EVERY'] == 0 and app_session.upload_count > 0:
        flash('🎉 Great job! You\'ve uploaded {} memes. Consider evaluating some more!'.format(config['PROMPT_EVAL_EVERY']))

    if request.method == 'POST':
        # Initialize form_data for template rendering
        form_data = {}
        # DEBUG
        print(f'Initial form_data: {form_data}')
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
            # DEBUG
            print(f'Extracted form_data: {form_data}')
            
            # Server-side validation (as backup to client-side)
            validation_errors = validate_form_data(form_data, app_session.current_user, config)

            # DEBUG
            print(f'Validation errors: {validation_errors}')
            
            if validation_errors:
                for error in validation_errors:
                    flash(error, 'error')
                return render_template('memes/upload.html', 
                                     current_user=app_session.current_user, 
                                     form_data=form_data)
            
            # Process and save file
            try:
                upload_folder = get_upload_folder(current_app)
                filename, original_filename = save_uploaded_file(file, upload_folder)
            except Exception as e:
                current_app.logger.error(f"File save error: {str(e)}\n{traceback.format_exc()}")
                flash(f'Error saving file: {str(e)}', 'error')
                return render_template('memes/upload.html', 
                                     current_user=app_session.current_user, 
                                     form_data=form_data)
            
            # Convert lists to strings/JSON as needed
            languages = ', '.join(form_data['languages']) if form_data['languages'] else ''
            humors = ', '.join(form_data['humors']) if form_data['humors'] else ''
            emotions_json = json.dumps(form_data['emotions'] if form_data['emotions'] else [])
            
            # Use current user data if available, otherwise form data
            if app_session.current_user:
                contributor_name = app_session.current_user['name']
                contributor_email = app_session.current_user['email']
                contributor_country = app_session.current_user['country']
                uploader_user_id = app_session.current_user['id']
            else:
                contributor_name = form_data.get('contributor_name', '')
                contributor_email = form_data.get('contributor_email', '')
                contributor_country = form_data.get('contributor_country', '')
                uploader_user_id = None
            
            # Validate session_id format
            if not app_session.session_id:
                current_app.logger.error("Invalid session_id: None or empty")
                flash('Session error: Please try again.', 'error')
                return render_template('memes/upload.html', 
                                     current_user=app_session.current_user, 
                                     form_data=form_data)
            
            # Save to database
            db = get_db()
            cursor = db.cursor()
            
            try:
                cursor.execute('''
                    INSERT INTO memes (
                        filename, original_filename, contributor_name, contributor_email,
                        contributor_country, platform_found, uploader_session, uploader_user_id,
                        meme_content, humor_type, emotions_conveyed, context_required,
                        terms_agreement
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    filename, original_filename, contributor_name, contributor_email,
                    contributor_country, form_data['platform_found'], 
                    app_session.session_id, uploader_user_id,
                    languages, humors, emotions_json, form_data['context_level'],
                    form_data['terms_agreement']
                ))
                
                meme_id = cursor.lastrowid
            except Exception as e:
                current_app.logger.error(f"Database insert error for memes: {str(e)}\n{traceback.format_exc()}")
                raise e
            
            # If humor_explanation is provided, insert into meme_descriptions table
            humor_explanation = form_data.get('humor_explanation')
            if humor_explanation:
                try:
                    cursor.execute('''
                        INSERT INTO meme_descriptions (
                            meme_id, description, is_original, uploader_user_id, uploader_session, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        meme_id,
                        humor_explanation,
                        1,  # is_original=True
                        uploader_user_id,
                        app_session.session_id,
                        datetime.datetime.now()
                    ))
                except Exception as e:
                    current_app.logger.error(f"Database insert error for meme_descriptions: {str(e)}\n{traceback.format_exc()}")
                    raise e
            
            # Update user stats if logged in
            # DEBUG 
            print(f'Check increment')
            if app_session.current_user:
                try:
                    app_session.increment_upload()
                    print(f'Increment done!')
                except Exception as e:
                    print(f'ERROR Increment')
                    current_app.logger.error(f"Error incrementing upload count: {str(e)}\n{traceback.format_exc()}")
                    raise e
            
            db.commit()
            
            flash('Meme uploaded and classified successfully! Thank you for your detailed contribution to our research.', 'success')
            
            # Check if we should prompt for evaluation
            if app_session.current_user and app_session.upload_count % config['PROMPT_EVAL_EVERY'] == 0 and app_session.upload_count >0:
                flash('🎯 You\'ve uploaded {} memes! Now help evaluate others to improve the dataset!'.format(config['PROMPT_EVAL_EVERY']), 'info')
            
            print(f"Redirecting user to Gallery")
            return redirect(url_for('memes.gallery'))
            
        except Exception as e:
            print(f"Error {str(e)}")
            current_app.logger.error(f"Upload error: {str(e)}\n{traceback.format_exc()}")
            db.rollback()
            flash(f'An error occurred while uploading: {str(e)}', 'error')
            return render_template('memes/upload.html', 
                                 current_user=app_session.current_user, 
                                 form_data=form_data)
    
    # GET request - show upload form
    return render_template('memes/upload.html', current_user=app_session.current_user)

def extract_and_validate_form_data(form):
    """Extract and clean form data"""
    return {
        # Meme Information
        'platform_found': form.get('platform_found', '').strip(),
        'languages': form.getlist('languages'),
        
        # Humor & Emotional Analysis
        'humor_explanation': form.get('humor_explanation', '').strip(),
        'humors': form.getlist('humors[]'),
        'emotions': form.getlist('emotions[]'),
        
        # Context & References
        'context_level': form.get('context_level', '').strip(),
        
        # Additional
        'terms_agreement': form.get('terms_agreement') == 'on',
        
        # Contributor info (for anon users)
        'contributor_name': form.get('contributor_name', '').strip(),
        'contributor_email': form.get('contributor_email', '').strip(),
        'contributor_country': form.get('contributor_country', '').strip(),
        'birth_year': form.get('birth_year', '').strip()
    }

def validate_form_data(form_data, current_user, config):
    """Validate form data and return list of errors"""
    errors = []
    
    # Required fields validation
    required_fields = [
        ('platform_found', 'Platform where found'),
        ('context_level', 'Context level'),
        ('languages', 'Languages'),
        ('humors', 'Humor types'),
        ('emotions', 'Emotions')
    ]
    
    for field, display_name in required_fields:
        if not form_data.get(field) or (isinstance(form_data[field], list) and len(form_data[field]) == 0):
            errors.append(f'{display_name} is required')
    
    # Validate platform_found against config.PLATFORM_OPTIONS
    if form_data.get('platform_found') and 'PLATFORM_OPTIONS' in config and form_data['platform_found'] not in config['PLATFORM_OPTIONS']:
        errors.append('Invalid platform selected')
    
    # Validate context_level
    valid_context_levels = ['Universal', 'Basic Internet', 'Pop Culture', 'Specialized']
    if form_data.get('context_level') and form_data['context_level'] not in valid_context_levels:
        errors.append('Invalid context level selected')
    
    # Anonymous user specific validation
    if not current_user:
        if not form_data.get('contributor_country'):
            errors.append('Country is required')
        if not form_data.get('birth_year'):
            errors.append('Birth year is required')
        elif not (form_data['birth_year'].isdigit() and 1900 <= int(form_data['birth_year']) <= 2025):
            errors.append('Birth year must be between 1900 and 2025')
    
    # Terms agreement validation
    if not form_data.get('terms_agreement'):
        errors.append('You must agree to the terms to upload')
    
    # Email validation (if provided)
    if form_data.get('contributor_email') and '@' not in form_data['contributor_email']:
        errors.append('Please provide a valid email address')
    
    return errors

@bp.route('/uploaded_file/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    upload_folder = get_upload_folder(current_app)
    return send_from_directory(upload_folder, filename)