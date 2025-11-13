# memeqa/routes/memes.py
from flask import Blueprint, render_template, request, abort, send_from_directory, current_app, flash, redirect, url_for, session,jsonify
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
    filter_type = request.args.get('filter', 'all')
    
    # Limit per_page options for security
    if per_page not in [4, 8, 16]:
        per_page = 4
    
    # Validate page number is positive
    if page < 1:
        abort(404)
    
    offset = (page - 1) * per_page
    
    # Get database connection
    db = get_db()

    current_user = get_current_user(db)

    # Restrict gallery to registered users only
    if not current_user:
        flash('Please register or log in to access the gallery.', 'error')
        return redirect(url_for('auth.register'))
    user_id = current_user['id'] if current_user else None
    
    # Build base queries depending on filter
    if filter_type == 'all':
        id_query = '''
            SELECT m.id
            FROM memes AS m
            LEFT JOIN evaluations AS e
                ON m.id = e.meme_id
                AND e.user_id = ?
            WHERE m.user_id = ? OR e.user_id = ?
            ORDER BY m.upload_date DESC
            LIMIT ? OFFSET ?
        '''
        count_query = '''
            SELECT COUNT(*) AS count
            FROM (
                SELECT m.id
                FROM memes AS m
                LEFT JOIN evaluations AS e
                    ON m.id = e.meme_id
                    AND e.user_id = ?
                WHERE m.user_id = ? OR e.user_id = ?
            )
        '''
        id_params = [user_id, user_id, user_id, per_page, offset]
        count_params = [user_id, user_id, user_id]

    elif filter_type == 'evaluated':
        id_query = '''
            SELECT m.id
            FROM memes AS m
            LEFT JOIN evaluations AS e
                ON m.id = e.meme_id
                AND e.user_id = ?
            WHERE e.user_id = ?
            ORDER BY m.upload_date DESC
            LIMIT ? OFFSET ?
        '''
        count_query = '''
            SELECT COUNT(*) AS count
            FROM (
                SELECT m.id
                FROM memes AS m
                LEFT JOIN evaluations AS e
                    ON m.id = e.meme_id
                    AND e.user_id = ?
                WHERE e.user_id = ?
            )
        '''
        id_params = [user_id, user_id, per_page, offset]
        count_params = [user_id, user_id]
    elif filter_type == 'own':
        id_query = '''
            SELECT m.id
            FROM memes AS m
            WHERE m.user_id = ?
            ORDER BY m.upload_date DESC
            LIMIT ? OFFSET ?
        '''
        count_query = '''
            SELECT COUNT(*) AS count
            FROM memes AS m
            WHERE m.user_id = ?
        '''
        id_params = [user_id, per_page, offset]
        count_params = [user_id]

    elif filter_type == 'liked':
        id_query = '''
            SELECT m.id
            FROM memes AS m
            LEFT JOIN meme_likes AS ml
                ON m.id = ml.meme_id
                AND ml.user_id = ?
            WHERE ml.user_id = ?
            ORDER BY m.upload_date DESC
            LIMIT ? OFFSET ?
        '''
        count_query = '''
            SELECT COUNT(*) AS count
            FROM (
                SELECT m.id
                FROM memes AS m
                LEFT JOIN meme_likes AS ml
                    ON m.id = ml.meme_id
                    AND ml.user_id = ?
                WHERE ml.user_id = ?
            )
        '''
        id_params = [user_id, user_id, per_page, offset]
        count_params = [user_id, user_id]
    else:
        abort(400)

    # Execute count
    total_count = db.execute(count_query, count_params).fetchone()['count']
   
    # Check if page is out of range
    max_page = (total_count + per_page - 1) // per_page if total_count > 0 else 1
    if page > max_page and total_count > 0:
        abort(404)

    # Fetch meme IDs
    rows = db.execute(id_query, id_params).fetchall()
    meme_ids = [row['id'] for row in rows]

    # Fetch meme details
    if meme_ids:
        placeholders = ','.join('?' for _ in meme_ids)
        memes = db.execute(f'''
            SELECT m.*,
                CASE WHEN ml.user_id IS NOT NULL THEN 1 ELSE 0 END AS liked_by_user
            FROM memes m
            LEFT JOIN meme_likes AS ml
                ON m.id = ml.meme_id AND ml.user_id = ?
            WHERE m.id IN ({placeholders})
            ORDER BY m.upload_date DESC
            ''', [user_id] + meme_ids).fetchall()
    else:
        memes = []
    
    # Create pagination object
    pagination = Pagination(page, per_page, total_count)
    pagination.items = memes
    
    return render_template('memes/gallery.html', 
                         memes=pagination,
                         per_page=per_page,
                         filter_type=filter_type)

# Like/unlike meme route
@bp.route('/like/<int:meme_id>', methods=['POST'])
def like_meme(meme_id):
    db = get_db()
    current_user = get_current_user(db)
    if not current_user:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = current_user['id']
    existing = db.execute(
        'SELECT 1 FROM meme_likes WHERE meme_id = ? AND user_id = ?',
        (meme_id, user_id)
    ).fetchone()

    if existing:
        db.execute(
            'DELETE FROM meme_likes WHERE meme_id = ? AND user_id = ?',
            (meme_id, user_id)
        )
        liked = False
    else:
        db.execute(
            'INSERT INTO meme_likes (meme_id, user_id) VALUES (?, ?)',
            (meme_id, user_id)
        )
        liked = True

    db.commit()

    # Get updated like count
    likes_count = db.execute(
        'SELECT COUNT(*) AS c FROM meme_likes WHERE meme_id = ?',
        (meme_id,)
    ).fetchone()['c']

    return jsonify({
        'liked': liked,
        'likes': likes_count
    })

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
                        contributor_country, platform_found, session_id, user_id,
                        languages, humor_type, emotions_conveyed, context_level,
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
                            meme_id, description, is_original, user_id, session_id, created_at
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

@bp.route('/meme/<int:meme_id>')
def meme_detail(meme_id):
    db = get_db()

    current_user = get_current_user(db)

    # Retrieve navigation state
    gallery_page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 4, type=int)
    filter_type = request.args.get('filter', 'all')

    user_id = current_user['id'] if current_user else None

    # # Restrict gallery to registered users only
    # if not current_user:
    #     flash('Please register or log in to view individual memes.', 'error')
    #     return redirect(url_for('auth.register'))

    # User’s own evaluation (if exists)
    user_eval = None
    if user_id:
        user_eval = db.execute(
            "SELECT * FROM evaluations WHERE meme_id = ? AND user_id = ?",
            (meme_id, user_id)
        ).fetchone()

    # Meme details
    meme = db.execute('SELECT * FROM memes WHERE id = ?', (meme_id,)).fetchone()

    is_user_owner = False
    if current_user and meme['user_id'] == current_user['id']:
        is_user_owner = True
        print(f'User {current_user["id"]} is owner of meme {meme_id}')

    # User has to have evaluated meme to view it or Own meme
    if not user_eval and not is_user_owner:
        flash('You need to evaluate this meme before viewing its details.', 'error')
        return redirect(url_for('memes.gallery'))
    

    # Build filtered meme id list for navigation consistency
    base_query = None
    params = None

    if filter_type == 'all':
        base_query = '''
            SELECT m.id
            FROM memes AS m
            LEFT JOIN evaluations AS e
                ON m.id = e.meme_id AND e.user_id = ?
            WHERE m.user_id = ? OR e.user_id = ?
            ORDER BY m.upload_date DESC
        '''
        params = [user_id, user_id, user_id]

    elif filter_type == 'evaluated':
        base_query = '''
            SELECT m.id
            FROM memes AS m
            JOIN evaluations AS e
                ON m.id = e.meme_id
            WHERE e.user_id = ?
            ORDER BY m.upload_date DESC
        '''
        params = [user_id]

    elif filter_type == 'own':
        base_query = '''
            SELECT id
            FROM memes
            WHERE user_id = ?
            ORDER BY upload_date DESC
        '''
        params = [user_id]

    elif filter_type == 'liked':
        base_query = '''
            SELECT m.id
            FROM memes AS m
            JOIN meme_likes AS ml
                ON m.id = ml.meme_id
            WHERE ml.user_id = ?
            ORDER BY m.upload_date DESC
        '''
        params = [user_id]

    # Fetch list of meme IDs in correct order
    meme_list = [row["id"] for row in db.execute(base_query, params).fetchall()]

    prev_id = None
    prev_page = gallery_page
    next_id = None
    next_page = gallery_page

    if meme_id in meme_list:
        idx = meme_list.index(meme_id)
        
        # Next meme
        if idx > 0:
            next_id = meme_list[idx - 1]
            next_page = get_meme_page(meme_list, next_id, per_page)
            
        # Previous meme
        if idx < len(meme_list) - 1:
            prev_id = meme_list[idx + 1]
            prev_page = get_meme_page(meme_list, prev_id, per_page)

    # Page for back-to-gallery
    gallery_page_for_current_meme = get_meme_page(meme_list, meme_id, per_page)



    # Likes count
    likes_count = db.execute(
        "SELECT COUNT(*) AS c FROM meme_likes WHERE meme_id = ?", 
        (meme_id,)
    ).fetchone()["c"]

    # Evaluations count
    eval_count = db.execute(
        "SELECT COUNT(*) AS c FROM evaluations WHERE meme_id = ?", 
        (meme_id,)
    ).fetchone()["c"]

    descriptions = db.execute(
        """
        SELECT
            md.*,
            CASE
                WHEN md.user_id = ?2 THEN 'You'
                ELSE u.name
            END AS uploader_name,
            de.vote,
            m.id AS meme_own
        FROM meme_descriptions md
        LEFT JOIN users u
            ON md.user_id = u.id
        LEFT JOIN description_evaluations de
            ON md.id = de.description_id
            AND de.user_id = ?2
        LEFT JOIN memes m
            ON md.meme_id = m.id
        WHERE md.meme_id = ?1
        AND (
                m.user_id = ?2              -- user owns the meme
                OR de.vote IS NOT NULL      -- user evaluated description
                OR md.user_id = ?2 -- user wrote the description
            )
        ORDER BY md.created_at DESC
        """,
        (meme_id, user_id)
    ).fetchall()

    # Did current user like this meme?
    liked_by_user = False
    if user_id:
        liked_by_user = db.execute(
            "SELECT 1 FROM meme_likes WHERE meme_id = ? AND user_id = ?",
            (meme_id, user_id)
        ).fetchone() is not None

    if not meme:
        abort(404)

    # If you later add descriptions, evaluations, etc., fetch them here
    # descriptions = ...

    return render_template(
        "memes/meme_detail.html",
        meme=meme,
        likes_count=likes_count,
        eval_count=eval_count,
        descriptions=descriptions,
        user_eval=user_eval,
        liked_by_user=liked_by_user,
        is_user_owner=is_user_owner,
        gallery_page=gallery_page_for_current_meme,  # correct page for back button
        per_page=per_page,
        filter_type=filter_type,
        prev_id=prev_id,
        prev_page=prev_page,
        next_id=next_id,
        next_page=next_page
    )

def get_meme_page(meme_list, target_id, per_page):
    """Return the page number where the target meme appears in meme_list"""
    if target_id not in meme_list:
        return 1
    idx = meme_list.index(target_id)  # 0-based index
    return (idx // per_page) + 1      # 1-based page number