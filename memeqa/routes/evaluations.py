# memeqa/routes/evaluations.py
from flask import Blueprint, render_template, redirect, url_for, flash, session, current_app, request
from memeqa.database import get_db
from memeqa.utils import get_current_user,AppSession
import json
import uuid
import random
import pandas as pd

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
    """Show next meme/description to evaluate."""

    db = get_db()
    user = get_current_user(db)
    app_session = AppSession(user)
    config = current_app.config
    limits = app_session.check_limits()

    # --- Limits checks ---
    if not app_session.current_user and not limits['can_evaluate']:
        flash(f"You've reached the limit of {config['ANON_MAX_EVAL']} evaluations. Please register or log in to continue!")
        return redirect(url_for('auth.register'))

    if app_session.current_user and app_session.eval_count % config['PROMPT_UPLOAD_EVERY'] == 0 and app_session.eval_count > 0:
        flash(f"🎉 Great job! You've evaluated {config['PROMPT_UPLOAD_EVERY']} memes. Consider uploading some of your own!")

    evaluation_count = app_session.eval_count
    user_id = user['id'] if user else None
    session_id = app_session.session_id if not user else None

    # --- STEP 1: Get possible memes/descriptions ---
    if user_id:
        memes_desc_table = db.execute("""
            SELECT
                m.id AS meme_id,
                COALESCE(md_other.id, -1) AS description_id,
                (SELECT COUNT(*) FROM meme_descriptions md_all WHERE md_all.meme_id = m.id) AS total_descriptions,
                CASE WHEN EXISTS (
                    SELECT 1 FROM meme_descriptions md_user
                    WHERE md_user.meme_id = m.id AND md_user.user_id = ?
                ) THEN 1 ELSE 0 END AS has_user_description
            FROM memes m
            LEFT JOIN meme_descriptions md_other
                ON m.id = md_other.meme_id AND md_other.user_id != ?
            WHERE m.user_id != ?
        """, (user_id, user_id, user_id)).fetchall()
    else:
        memes_desc_table = db.execute("""
            SELECT
                m.id AS meme_id,
                COALESCE(md_other.id, -1) AS description_id,
                (SELECT COUNT(*) FROM meme_descriptions md_all WHERE md_all.meme_id = m.id) AS total_descriptions,
                CASE WHEN EXISTS (
                    SELECT 1 FROM meme_descriptions md_user
                    WHERE md_user.meme_id = m.id AND md_user.session_id = ?
                ) THEN 1 ELSE 0 END AS has_user_description
            FROM memes m
            LEFT JOIN meme_descriptions md_other
                ON m.id = md_other.meme_id AND md_other.session_id != ?
            WHERE m.session_id != ?
        """, (session_id, session_id, session_id)).fetchall()

    if not memes_desc_table:
        flash('No memes available to evaluate yet. Try uploading some!')
        return redirect(url_for('memes.upload_file'))

    # --- STEP 2: Get completed evaluations ---
    if user_id:
        evaluated_rows = db.execute("""
            SELECT e.meme_id, COALESCE(de.description_id, -1) AS evaluated_description_id
            FROM evaluations e
            LEFT JOIN description_evaluations de
                ON e.meme_id = de.meme_id AND de.user_id = e.user_id
            WHERE e.user_id = ?
        """, (user_id,)).fetchall()
    else:
        evaluated_rows = db.execute("""
            SELECT e.meme_id, COALESCE(de.description_id, -1) AS evaluated_description_id
            FROM evaluations e
            LEFT JOIN description_evaluations de
                ON e.meme_id = de.meme_id AND de.session_id = e.session_id
            WHERE e.session_id = ?
        """, (session_id,)).fetchall()

    memes_df = pd.DataFrame([dict(row) for row in memes_desc_table])
    if evaluated_rows:
        evaluated_df = pd.DataFrame([dict(row) for row in evaluated_rows])
    else:
    # empty DataFrame with expected columns
        evaluated_df = pd.DataFrame(columns=['meme_id', 'evaluated_description_id'])

    print("Memes DataFrame:")
    print(memes_df)
    print("Evaluated DataFrame:")
    print(evaluated_df)

    # --- STEP 3: Merge and filter available pairs ---
    merged_df = memes_df.merge(
        evaluated_df,
        left_on=['meme_id', 'description_id'],
        right_on=['meme_id', 'evaluated_description_id'],
        how='left',
        suffixes=('_possible','_evaluated')
    )

    available_df = merged_df[
        (merged_df['evaluated_description_id'].isna()) |
        ((merged_df['description_id'] == -1) & (merged_df['has_user_description'] == 0) & (merged_df['total_descriptions'] < 4))
    ]

    if available_df.empty:
        flash('🎉 You have evaluated all available memes/descriptions!')
        return render_template('evaluations/evaluate.html', meme=None)

    # --- STEP 4: Build options set and pick random ---
    options_set = set(
        zip(available_df['meme_id'], available_df['description_id'])
    )
    selected_pair = random.choice(list(options_set))
    meme_id, description_id = selected_pair

    # --- STEP 5: Get full meme and description data ---
    meme = db.execute('SELECT * FROM memes WHERE id = ?', (meme_id,)).fetchone()
    description = None
    if description_id != -1:
        desc_row = db.execute('SELECT * FROM meme_descriptions WHERE id = ?', (description_id,)).fetchone()
        description = desc_row['description'] if desc_row else None

    description_count = db.execute(
        'SELECT COUNT(*) AS count FROM meme_descriptions WHERE meme_id = ?',
        (meme_id,)
    ).fetchone()['count']

    # --- STEP 6: Current evaluation status ---
    eval_row = db.execute('''
        SELECT evaluated_humor_type, evaluated_emotions, evaluated_context_level, de.vote
        FROM evaluations e
        LEFT JOIN description_evaluations de 
            ON e.meme_id = de.meme_id 
        WHERE e.meme_id = ? 
        AND e.user_id = ? 
        AND (de.description_id = ? OR (? = -1 AND de.description_id IS NULL))
    ''', (meme_id, user_id, description_id, description_id)).fetchone()

    eval_status = {
        "humor_done": bool(eval_row and eval_row['evaluated_humor_type'] is not None),
        "emotion_done": bool(eval_row and eval_row['evaluated_emotions'] is not None),
        "context_done": bool(eval_row and eval_row['evaluated_context_level'] is not None),
        "description_done": bool(eval_row and eval_row['vote'] is not None)
    }

    return render_template(
        'evaluations/evaluate.html',
        meme=meme,
        evaluation_count=evaluation_count,
        eval_mems=config['EVAL_COUNT'],
        can_upload=limits['can_upload'],
        description=description,
        description_id=description_id,
        description_count=description_count,
        eval_status=eval_status,
        development=config['DEVELOPMENT']
    )


# @bp.route('/')
# def evaluate():
#     """Show next meme/description to evaluate."""

#     db = get_db()
#     user = get_current_user(db)
#     app_session = AppSession(user)

#     config = current_app.config
#     limits = app_session.check_limits()

#     # Check limits for anonymous users
#     if not app_session.current_user and not limits['can_evaluate']:
#         flash('You\'ve reached the limit of {} evaluations. Please register or log in to continue!'.format(config['ANON_MAX_EVAL']))
#         return redirect(url_for('auth.register'))

#     # Check if registered user should be prompted to upload
#     if app_session.current_user and app_session.eval_count % config['PROMPT_UPLOAD_EVERY'] == 0 and app_session.eval_count > 0:
#         flash('🎉 Great job! You\'ve evaluated {} memes. Consider uploading some of your own!'.format(config['PROMPT_UPLOAD_EVERY']))

#     # Get counts
#     evaluation_count = app_session.eval_count
#     user_id = user['id'] if user else None

#     # --- STEP 1: Get all possible (meme_id, description_id) pairs not uploaded by user ---
#     # This includes memes without descriptions (description_id = NULL)
#     if user_id:
#         possible_pairs = db.execute('''
#             SELECT 
#                 m.id as meme_id,
#                 md.id as description_id,
#                 md.description
#             FROM memes m
#             LEFT JOIN meme_descriptions md 
#                 ON m.id = md.meme_id 
#                 AND md.uploader_user_id != ?
#             WHERE m.uploader_user_id != ?
#         ''', (user_id,user_id)).fetchall()
#     else:
#         possible_pairs = db.execute('''
#             SELECT 
#                 m.id as meme_id,
#                 md.id as description_id,
#                 md.description
#             FROM memes m
#             LEFT JOIN meme_descriptions md 
#                 ON m.id = md.meme_id
#                 AND md.uploader_session != ?
#             WHERE m.uploader_session != ?
#         ''', (app_session.session_id,app_session.session_id)).fetchall()

#     if not possible_pairs:
#         flash('No memes available to evaluate yet. Try uploading some!')
#         return redirect(url_for('memes.upload_file'))

#     # Convert to set of (meme_id, description_id) tuples for efficient lookup
#     possible_set = {(row['meme_id'], row['description_id']) for row in possible_pairs}
    
#     # Create lookup dictionary for full row data
#     pair_data = {(row['meme_id'], row['description_id']): row for row in possible_pairs}

#     # --- STEP 2: Get all completed evaluations by this user ---
#     # An evaluation is "complete" when all 4 aspects are evaluated:
#     # humor_score, emotion_label, context, description_feedback
#     if user_id:
#         completed_evaluations = db.execute('''
#             SELECT 
#                 e.meme_id,
#                 de.description_id,
#                 e.evaluated_humor_type,
#                 e.evaluated_emotions,
#                 e.evaluated_context_level,
#                 de.vote
#             FROM evaluations e
#             LEFT JOIN description_evaluations de 
#                 ON e.meme_id = de.meme_id 
#             WHERE e.user_id = ? and de.user_id = ?
#         ''', (user_id,user_id)).fetchall()
#     else:
#         completed_evaluations = db.execute('''
#             SELECT 
#                 e.meme_id,
#                 de.description_id,
#                 e.evaluated_humor_type,
#                 e.evaluated_emotions,
#                 e.evaluated_context_level,
#                 de.vote
#             FROM evaluations e
#             LEFT JOIN description_evaluations de 
#                 ON e.meme_id = de.meme_id
#             WHERE e.session_id = ? and de.session_id = ?
#         ''', (app_session.session_id,app_session.session_id)).fetchall()

#     # Filter to only fully completed evaluations
#     completed_set = {
#         (row['meme_id'], row['description_id'])
#         for row in completed_evaluations
#         if all([
#             row['evaluated_humor_type'] is not None,
#             row['evaluated_emotions'] is not None,
#             row['evaluated_context_level'] is not None,
#             row['vote'] is not None
#         ])
#     }

#     # --- STEP 3: Set difference - remove completed from possible ---
#     available_set = possible_set - completed_set

#     if not available_set:
#         flash('🎉 You have evaluated all available memes/descriptions!')
#         return render_template('evaluations/evaluate.html', meme=None)

#     # --- STEP 4: Pick one random pair ---
#     selected_pair = random.choice(list(available_set))
#     selected_data = pair_data[selected_pair]
#     meme_id, description_id = selected_pair

#     # --- Get additional info for display ---
#     # Get full meme data
#     meme = db.execute('SELECT * FROM memes WHERE id = ?', (meme_id,)).fetchone()
    
#     # Get description if exists
#     description = None
#     if description_id:
#         description = db.execute(
#             'SELECT * FROM meme_descriptions WHERE id = ?',
#             (description_id,)
#         ).fetchone()
#         description = description['description'] if description else None

#     # Count descriptions for this meme
#     description_count = db.execute(
#         'SELECT COUNT(*) as count FROM meme_descriptions WHERE meme_id = ?',
#         (meme_id,)
#     ).fetchone()['count']

#     # Get current evaluation status (what's already done)
#     eval_row = db.execute('''
#         SELECT evaluated_humor_type, evaluated_emotions, evaluated_context_level, de.vote
#         FROM evaluations e
#         LEFT JOIN description_evaluations de 
#             ON e.meme_id = de.meme_id 
#         WHERE e.meme_id = ? 
#         AND e.user_id = ? 
#         AND (de.description_id = ? OR (? IS NULL AND de.description_id IS NULL))
#     ''', (meme_id, user_id, description_id, description_id)).fetchone()

#     eval_status = {
#         "humor_done": bool(eval_row and eval_row['evaluated_humor_type'] is not None),
#         "emotion_done": bool(eval_row and eval_row['evaluated_emotions'] is not None),
#         "context_done": bool(eval_row and eval_row['evaluated_context_level'] is not None),
#         "description_done": bool(eval_row and eval_row['vote'] is not None)
#     }

#     return render_template(
#         'evaluations/evaluate.html',
#         meme=meme,
#         evaluation_count=evaluation_count,
#         eval_mems=config['EVAL_COUNT'],
#         can_upload=app_session.check_limits()['can_upload'],
#         description=description,
#         description_id=description_id,
#         description_count=description_count,
#         eval_status=eval_status,
#         development=config['DEVELOPMENT']
#     )
    

@bp.route('/evaluate_meme', methods=['POST'])
def evaluate_meme():
    """Save meme evaluation and related feedback."""
    db = get_db()
    user = get_current_user(db)
    user_id = user['id'] if user else None
    session_id = session.get('session_id')  # for anonymous users
    config = current_app.config

    meme_id = request.form.get('meme_id')
    evaluation_time = request.form.get('evaluation_time')
    humor_list = request.form.getlist('humors[]')
    emotion_list = request.form.getlist('emotions[]')
    context_level = request.form.get('context_level')
    desc_id = request.form.get('description_id')
    description_feedback = request.form.get('description_feedback')
    new_description = request.form.get('new_description')
    like_meme = request.form.get('like_meme')

    print("Received evaluation:", {
        'meme_id': meme_id,
        'evaluation_time': evaluation_time,
        'humor_list': humor_list,
        'emotion_list': emotion_list,
        'context_level': context_level,
        'desc_id': desc_id,
        'description_feedback': description_feedback,
        'new_description': new_description,
        'like_meme': like_meme,
        'session_id': session_id,
        'user_id': user_id
    })

    if not meme_id:
        flash('Invalid meme data.')
        return redirect(url_for('evaluations.evaluate'))

    try:
        db.execute('BEGIN TRANSACTION')

        # Insert or update the evaluation
        existing_eval = db.execute('''
            SELECT * FROM evaluations
            WHERE meme_id = ? AND ((user_id = ?) OR (session_id = ?))
        ''', (meme_id, user_id, session_id)).fetchone()

        print("Existing evaluation found:", existing_eval)

        humor_json = json.dumps(humor_list) if humor_list else None
        emotion_json = json.dumps(emotion_list) if emotion_list else None

        if existing_eval:
            db.execute('''
                UPDATE evaluations
                SET evaluated_humor_type = COALESCE(?, evaluated_humor_type),
                    evaluated_emotions = COALESCE(?, evaluated_emotions),
                    evaluated_context_level = COALESCE(?, evaluated_context_level),
                    evaluation_time_seconds = COALESCE(?, evaluation_time_seconds),
                    evaluation_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (humor_json, emotion_json, context_level, evaluation_time, existing_eval['id']))
        else:
            print("Inserting new evaluation for meme_id:", meme_id)
            db.execute('''
                INSERT INTO evaluations (session_id, user_id, meme_id, evaluated_humor_type,
                                         evaluated_emotions, evaluated_context_level, evaluation_time_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (session_id, user_id, meme_id, humor_json, emotion_json, context_level, evaluation_time))
            print("Inserted new evaluation for meme_id:", meme_id)

        if user_id:
            # --- Handle meme like ---
            if like_meme == '1':
                existing_like = db.execute('''
                    SELECT id FROM meme_likes
                    WHERE meme_id = ? AND ((user_id = ?))
                ''', (meme_id, user_id)).fetchone()

                if not existing_like:
                    db.execute('''
                        INSERT INTO meme_likes (meme_id, user_id, session_id)
                        VALUES (?, ?, ?)
                    ''', (meme_id, user_id, session_id))

        # --- Handle description feedback ---
        if description_feedback:
            # Convert feedback to numeric vote
            vote_value = 1 if description_feedback == 'like' else -1

            if desc_id:
                existing_desc_eval = db.execute('''
                    SELECT id FROM description_evaluations
                    WHERE description_id = ? AND ((user_id = ?) OR (session_id = ?))
                ''', (desc_id, user_id, session_id)).fetchone()

                if not existing_desc_eval:
                    db.execute('''
                        INSERT INTO description_evaluations (description_id, meme_id, user_id, session_id, vote)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (desc_id, meme_id, user_id, session_id, vote_value))

        # --- Handle new description suggestion ---
        if new_description and new_description.strip():
            desc_count = db.execute('SELECT COUNT(*) FROM meme_descriptions WHERE meme_id = ?', (meme_id,)).fetchone()[0]
            if desc_count < config['MAX_DESCRIPTIONS_PER_MEME']:
                db.execute('''
                    INSERT INTO meme_descriptions (meme_id, description, is_original, user_id, session_id)
                    VALUES (?, ?, 0, ?, ?)
                ''', (meme_id, new_description.strip(), user_id, session_id))
            else:
                str_flash = '⚠️ This meme already has {} descriptions. New ones won’t be saved.'.format(config['MAX_DESCRIPTIONS_PER_MEME'])
                flash(str_flash)

        db.commit()
        flash('✅ Evaluation saved!')
        return redirect(url_for('evaluations.evaluate'))

    except Exception as e:
        db.rollback()
        print("Error saving evaluation:", e)
        flash('❌ Error saving evaluation. Try again.')
        return redirect(url_for('evaluations.evaluate'))