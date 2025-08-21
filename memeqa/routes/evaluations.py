# memeqa/routes/evaluations.py
from flask import Blueprint, render_template, redirect, url_for, flash, session, current_app, request
from memeqa.database import get_db
from memeqa.utils import get_current_user, check_anonymous_limits, should_prompt_upload
import json
import uuid

bp = Blueprint('evaluations', __name__)

def get_or_create_session():
    """Get or create session for tracking evaluations"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

def get_user_evaluation_count():
    """Get number of evaluations completed by current session or user"""
    db = get_db()
    current_user = get_current_user(db)
    session_id = get_or_create_session()
    
    if current_user:
        count = db.execute(
            'SELECT COUNT(*) as count FROM evaluations WHERE user_id = ?',
            (current_user['id'],)
        ).fetchone()['count']
    else:
        count = db.execute(
            'SELECT COUNT(*) as count FROM evaluations WHERE session_id = ? AND user_id IS NULL',
            (session_id,)
        ).fetchone()['count']
    
    return count

def get_available_memes_count():
    """Get count of memes available for evaluation"""
    db = get_db()
    count = db.execute('SELECT COUNT(*) as count FROM memes').fetchone()['count']
    return count

def can_user_upload():
    """Check if user can upload"""
    evaluation_count = get_user_evaluation_count()
    available_memes = get_available_memes_count()
    return evaluation_count >= current_app.config['EVAL_COUNT'] or \
           available_memes < current_app.config['MIN_MEME_COUNT']

def get_random_meme_for_evaluation():
    """Get a random meme that the user hasn't evaluated yet (and didn't upload)"""
    db = get_db()
    current_user = get_current_user(db)
    session_id = get_or_create_session()
    
    if current_user:
        # Registered users can't evaluate their own memes
        meme = db.execute('''
            SELECT * FROM memes 
            WHERE humor_type IS NOT NULL 
            AND emotions_conveyed IS NOT NULL 
            AND uploader_user_id != ?  -- Exclude user's own memes
            AND id NOT IN (
                SELECT meme_id FROM evaluations WHERE user_id = ?
            ) 
            ORDER BY RANDOM() LIMIT 1
        ''', (current_user['id'], current_user['id'])).fetchone()
    else:
        # Anonymous users can evaluate any meme they haven't evaluated
        meme = db.execute('''
            SELECT * FROM memes 
            WHERE humor_type IS NOT NULL 
            AND emotions_conveyed IS NOT NULL 
            AND id NOT IN (
                SELECT meme_id FROM evaluations 
                WHERE session_id = ? AND user_id IS NULL
            ) 
            ORDER BY RANDOM() LIMIT 1
        ''', (session_id,)).fetchone()
    
    return meme

@bp.route('/')
def evaluate():
    """Show humor/emotion evaluation page with limits"""
    EVAL_COUNT = current_app.config['EVAL_COUNT']
    MIN_MEME_COUNT = current_app.config['MIN_MEME_COUNT']
    
    db = get_db()
    current_user = get_current_user(db)
    session_id = get_or_create_session()
    
    # Check limits for anonymous users
    if not current_user:
        can_upload, can_evaluate, uploads, evaluations = check_anonymous_limits(db, session_id)
        if not can_evaluate:
            flash('You\'ve reached the limit of 5 evaluations. Please register or log in to continue!')
            return redirect(url_for('auth.register'))
    else:
        # Check if registered user should be prompted to upload
        if should_prompt_upload(current_user['total_evaluations']):
            flash('🎉 Great job! You\'ve evaluated 10 memes. Consider uploading some of your own!')
    
    # Get counts
    evaluation_count = get_user_evaluation_count()
    available_memes = get_available_memes_count()
    
    # Check if there are enough memes to evaluate
    if available_memes < MIN_MEME_COUNT:
        flash(f'Only {available_memes} memes available for evaluation. Help us by uploading more!')
        return redirect(url_for('memes.upload_file'))
    
    # Get a random meme to evaluate
    meme = get_random_meme_for_evaluation()
    
    if not meme:
        if current_user:
            flash('No more memes available for you to evaluate. You may have evaluated all available memes or they are all your uploads!')
        else:
            flash('No more memes available for evaluation. You can now upload your own!')
        return redirect(url_for('memes.upload_file'))
    
    return render_template('evaluations/evaluate.html', 
                         meme=meme, 
                         evaluation_count=evaluation_count,
                         current_user=current_user,
                         eval_mems=EVAL_COUNT,
                         memes_min=MIN_MEME_COUNT)

@bp.route('/submit', methods=['POST'])
def submit_humor_emotion_evaluation():
    """Submit humor and emotion evaluation"""
    db = get_db()
    current_user = get_current_user(db)
    session_id = get_or_create_session()
    
    meme_id = request.form.get('meme_id')
    evaluated_humor_type = request.form.get('humor_type')
    evaluated_emotions = request.form.getlist('emotions')
    evaluated_context_level = request.form.get('context_level', '')
    evaluation_time = request.form.get('evaluation_time', 0, type=int)
    confidence_level = request.form.get('confidence_level', 3, type=int)
    
    if not meme_id or not evaluated_humor_type or not evaluated_emotions:
        flash('Please complete all required fields.')
        return redirect(url_for('evaluations.evaluate'))
    
    # Get the meme to compare against
    meme = db.execute('''
        SELECT humor_type, emotions_conveyed 
        FROM memes 
        WHERE id = ?
    ''', (meme_id,)).fetchone()
    
    if not meme:
        flash('Meme not found.')
        return redirect(url_for('evaluations.evaluate'))
    
    # Calculate correctness scores
    try:
        # Check humor type match
        original_humor_type = meme['humor_type']
        matches_humor_type = (evaluated_humor_type == original_humor_type) if original_humor_type else None
        
        # Calculate emotion overlap
        emotion_overlap_score = 0.0
        if meme['emotions_conveyed']:
            try:
                original_emotions = json.loads(meme['emotions_conveyed'])
                if isinstance(original_emotions, list) and len(original_emotions) > 0:
                    evaluated_set = set(evaluated_emotions)
                    original_set = set(original_emotions)
                    
                    if len(original_set) > 0:
                        intersection = len(evaluated_set.intersection(original_set))
                        union = len(evaluated_set.union(original_set))
                        emotion_overlap_score = intersection / union if union > 0 else 0.0
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Convert emotions to JSON
        emotions_json = json.dumps(evaluated_emotions)
        
        # Save evaluation
        db.execute('''
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
            1 if matches_humor_type else 0 if matches_humor_type is not None else None,
            emotion_overlap_score,
            confidence_level, 
            evaluation_time
        ))
        
        # Update user stats if logged in
        if current_user:
            # Get user's evaluation count
            user_eval_count = db.execute(
                'SELECT COUNT(*) as count FROM evaluations WHERE user_id = ?',
                (current_user['id'],)
            ).fetchone()['count']
            
            # Update user's total evaluations
            db.execute('''
                UPDATE users 
                SET total_evaluations = ?
                WHERE id = ?
            ''', (user_eval_count, current_user['id']))
        
        db.commit()
        
        evaluation_count = get_user_evaluation_count()
        
        # Provide feedback
        feedback_parts = []
        
        if matches_humor_type is not None:
            if matches_humor_type:
                feedback_parts.append("✅ Humor type correct!")
            else:
                feedback_parts.append(f"🔍 Humor: You said '{evaluated_humor_type}', original was '{original_humor_type}'")
        
        if emotion_overlap_score > 0:
            if emotion_overlap_score >= 0.7:
                feedback_parts.append("✅ Great emotion match!")
            elif emotion_overlap_score >= 0.3:
                feedback_parts.append("🔍 Good emotion overlap!")
            else:
                feedback_parts.append("🔍 Some emotion differences noted")
        
        feedback = " | ".join(feedback_parts) if feedback_parts else "Thanks for your evaluation!"
        flash(f'{feedback} Progress: {evaluation_count}/{current_app.config["EVAL_COUNT"]} evaluations completed.')
        
    except Exception as e:
        print(f"Error processing evaluation: {e}")
        flash('Error processing evaluation. Please try again.')
        db.rollback()
        return redirect(url_for('evaluations.evaluate'))
    
    evaluation_count = get_user_evaluation_count()
    
    if evaluation_count >= current_app.config['EVAL_COUNT']:
        flash('🎉 Congratulations! You have completed all evaluations. You can now upload your own meme!')
        return redirect(url_for('memes.upload_file'))
    else:
        return redirect(url_for('evaluations.evaluate'))