# memeqa/routes/evaluations.py
from flask import Blueprint, render_template, redirect, url_for, flash, session, current_app, request
from memeqa.database import get_db
from memeqa.utils import get_current_user,AppSession
import json
import uuid

bp = Blueprint('evaluations', __name__)


def get_random_meme_for_evaluation(app_session):
    """Get a random meme that the user hasn't uploaded"""
    db = get_db()
    own_meme_ids = app_session.get_own_meme_ids()
    query = '''
        SELECT * FROM memes 
        WHERE humor_type IS NOT NULL 
        AND emotions_conveyed IS NOT NULL 
        AND id NOT IN ({})  -- Exclude user's own memes
        ORDER BY RANDOM() LIMIT 1
    '''.format(','.join('?' * len(own_meme_ids)) if own_meme_ids else '0')

    meme = db.execute(query, tuple(own_meme_ids) if own_meme_ids else ()).fetchone()
    return meme

@bp.route('/')
def evaluate():
    """Show humor/emotion evaluation page with limits"""

    app_session = AppSession(get_current_user(get_db()))
    config = current_app.config
    limits = app_session.check_limits()


    # Check limits for anonymous users
    if not app_session.current_user and not limits['can_evaluate']:
        flash('You\'ve reached the limit of {} evaluations. Please register or log in to continue!'.format(config['ANON_MAX_EVAL']))
        return redirect(url_for('auth.register'))

    # Check if registered user should be prompted to upload
    if app_session.current_user and app_session.eval_count % config['PROMPT_UPLOAD_EVERY'] == 0 and app_session.eval_count > 0:
        flash('🎉 Great job! You\'ve evaluated {} memes. Consider uploading some of your own!'.format(config['PROMPT_UPLOAD_EVERY']))

    # Get counts
    evaluation_count = app_session.eval_count
    available_memes = app_session.get_available_memes()

    print(f"Evaluation limits: {limits}\ncounts: eval={evaluation_count}, memes={available_memes}")

    # Check if there are enough memes to evaluate
    if available_memes < config['MIN_MEME_COUNT']:
        flash(f'Only {available_memes} memes available for evaluation. Help us by uploading more!')
        return redirect(url_for('memes.upload_file'))

    # Get a random meme to evaluate
    meme = get_random_meme_for_evaluation(app_session)

    if not meme:
        if app_session.current_user:
            flash('No more memes available for you to evaluate. You may have evaluated all available memes.')
            return redirect(url_for('memes.upload_file'))
        if not app_session.current_user and limits['can_upload']:
            flash('No more memes available. You can help by uploading some of your own!')
            return redirect(url_for('memes.upload_file'))
        else:
            flash('No more memes available. Please register to access more.')
            return redirect(url_for('auth.register'))
    
    return render_template('evaluations/evaluate.html',
                         meme=meme,
                         evaluation_count=evaluation_count,
                         eval_mems=config['EVAL_COUNT'],
                         can_upload=app_session.check_limits()['can_upload'],
                         development=config['DEVELOPMENT'])


@bp.route('/process', methods=['POST'])
def process_evaluation():
    """Process humor/emotion evaluation submission"""
    app_session = AppSession(get_current_user(get_db()))
    config = current_app.config
    
    # Check limits for anonymous users
    limits = app_session.check_limits()
    if not app_session.current_user and not limits['can_evaluate']:
        flash('You\'ve reached the evaluation limit. Please register to continue.')
        return redirect(url_for('auth.register'))

    try:
        meme_id = int(request.form.get('meme_id'))
        evaluated_humor_type = request.form.get('humor_type')
        evaluated_emotions = request.form.getlist('emotions[]')
        evaluated_context_level = request.form.get('context_level')
        confidence_level = int(request.form.get('confidence_level', 3))
        evaluation_time = int(request.form.get('evaluation_time', 0))
    except Exception as e:
        flash('Invalid form data. Please try again.')
        return redirect(url_for('evaluations.evaluate'))

    db = get_db()
    
    try:
        db.execute('BEGIN TRANSACTION')
        
        # Get original meme to compare against
        meme = db.execute('''
            SELECT humor_type, emotions_conveyed 
            FROM memes 
            WHERE id = ?
        ''', (meme_id,)).fetchone()
        
        if not meme:
            flash('Meme not found.')
            return redirect(url_for('evaluations.evaluate'))
        
        # Calculate correctness scores
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
            app_session.session_id, 
            app_session.user_id, 
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
        if app_session.current_user:
            app_session.increment_evaluation()
        else:
            # For anon, just refresh counts
            app_session._load_stats()
        
        db.commit()
        
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
        progress_t = f'/{app_session.max_eval}' if not app_session.current_user else ''

        flash(f'{feedback} Progress: {app_session.eval_count}{progress_t} evaluations completed.')
        
    except Exception as e:
        print(f"Error processing evaluation: {e}")
        flash('Error processing evaluation. Please try again.')
        db.rollback()
        return redirect(url_for('evaluations.evaluate'))
    
    if app_session.eval_count >= config['EVAL_COUNT']:
        flash('🎉 Congratulations! You have completed all evaluations. You can now upload your own meme!')
        return redirect(url_for('memes.upload_file'))
    else:
        return redirect(url_for('evaluations.evaluate'))
