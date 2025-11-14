from flask import Blueprint, render_template, session, current_app, abort, jsonify, flash, redirect, url_for
from memeqa.database import get_db
from memeqa.utils import get_current_user,AppSession
import uuid
import json
from datetime import datetime

bp = Blueprint('main', __name__)

def get_or_create_session():
    """Get or create session for tracking evaluations"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

def get_evaluation_count():
    """Get evaluation count for current session"""
    session_id = get_or_create_session()
    db = get_db()
    
    result = db.execute(
        'SELECT COUNT(*) as count FROM evaluations WHERE session_id = ?',
        (session_id,)
    ).fetchone()
    
    return result['count'] if result else 0

@bp.route('/')
def index():
    # Get config values
    EVAL_COUNT = current_app.config['EVAL_COUNT']
    MIN_MEME_COUNT = current_app.config['MIN_MEME_COUNT']
    DEVELOPMENT = current_app.config['DEVELOPMENT']

    # Create/get session
    session_id = get_or_create_session()

    # Get database connection
    db = get_db()
    current_user = get_current_user(db)
    
    # Get actual counts
    available_memes = db.execute('SELECT COUNT(*) as count FROM memes').fetchone()['count']
    evaluation_count = get_evaluation_count()
    
    # Leaderboards (registered users only)
    top_uploaders = db.execute('''
        SELECT name, total_submissions
        FROM users
        WHERE is_active = 1
        ORDER BY total_submissions DESC
        LIMIT 5
    ''').fetchall()

    top_evaluators = db.execute('''
        SELECT name, total_evaluations
        FROM users
        WHERE is_active = 1
        ORDER BY total_evaluations DESC
        LIMIT 5
    ''').fetchall()
    
    return render_template('main/index.html',
        current_user=current_user,
        evaluation_count=evaluation_count,  # Now tracking!
        eval_mems=EVAL_COUNT,
        memes_min=MIN_MEME_COUNT,
        available_memes=available_memes,
        development=DEVELOPMENT,
        top_uploaders=top_uploaders,
        top_evaluators=top_evaluators,
    )

@bp.route('/stats')
def stats():
    """Show basic statistics"""
    db = get_db()
    
    total_memes = db.execute('SELECT COUNT(*) as count FROM memes').fetchone()['count']
    total_evaluations = db.execute('SELECT COUNT(*) as count FROM evaluations').fetchone()['count']
    unique_evaluators = db.execute('SELECT COUNT(DISTINCT session_id) as count FROM evaluations').fetchone()['count']
    
    # Get registered users count safely
    try:
        registered_users = db.execute('SELECT COUNT(*) as count FROM users WHERE is_active = 1').fetchone()['count']
    except:
        registered_users = 0
    
    return render_template('main/stats.html', 
                         total_memes=total_memes,
                         total_evaluations=total_evaluations,
                         unique_evaluators=unique_evaluators,
                         registered_users=registered_users)

@bp.route('/analytics')
def analytics():
    """Research analytics dashboard"""
    db = get_db()
    
    try:
        # Basic stats
        total_memes = db.execute('SELECT COUNT(*) as count FROM memes').fetchone()['count']
        total_evaluations = db.execute('SELECT COUNT(*) as count FROM evaluations').fetchone()['count']
        unique_evaluators = db.execute('SELECT COUNT(DISTINCT session_id) as count FROM evaluations').fetchone()['count']
        
        try:
            registered_contributors = db.execute('SELECT COUNT(*) as count FROM users WHERE is_active = 1').fetchone()['count']
        except:
            registered_contributors = 0
        
        # Accuracy statistics
        accuracy_query = '''
            SELECT 
                AVG(CASE WHEN was_correct THEN 1.0 ELSE 0.0 END) as overall_accuracy,
                COUNT(CASE WHEN was_correct THEN 1 END) as correct_evaluations,
                COUNT(*) as total_evaluations
            FROM evaluations
            WHERE was_correct IS NOT NULL
        '''
        
        try:
            accuracy_stats_raw = db.execute(accuracy_query).fetchone()
            
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
        
        # Country distribution
        try:
            country_stats = db.execute('''
                SELECT contributor_country as country_of_submission, COUNT(*) as count 
                FROM memes 
                WHERE contributor_country IS NOT NULL AND contributor_country != ''
                GROUP BY contributor_country 
                ORDER BY count DESC 
                LIMIT 10
            ''').fetchall()
        except:
            country_stats = []
        
        # Platform distribution
        try:
            platform_stats = db.execute('''
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
            humor_stats = db.execute('''
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
            cultural_stats = db.execute('''
                SELECT cultural_reach, COUNT(*) as count 
                FROM memes 
                WHERE cultural_reach IS NOT NULL AND cultural_reach != ''
                GROUP BY cultural_reach 
                ORDER BY count DESC
            ''').fetchall()
        except:
            cultural_stats = []
        
        # Most difficult memes (lowest accuracy)
        try:
            difficult_memes = db.execute('''
                SELECT m.id, m.original_filename, 
                       COALESCE(m.meme_content, 'No description') as meme_content, 
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
            easy_memes = db.execute('''
                SELECT m.id, m.original_filename, 
                       COALESCE(m.meme_content, 'No description') as meme_content, 
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
    
    return render_template('main/analytics.html',
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
                         easy_memes=easy_memes)

@bp.route('/export_data')
def export_data():
    """Export research data (for researchers)"""
    if not current_app.config.get('DEVELOPMENT', False):
        abort(403)
    
    db = get_db()
    
    # Get all meme data with analytics
    memes_data = db.execute('''
        SELECT m.*, a.accuracy_rate, a.total_evaluations as analytics_evaluations,
               a.difficulty_score, a.avg_evaluation_time, a.avg_confidence_level
        FROM memes m
        LEFT JOIN meme_analytics a ON m.id = a.meme_id
        ORDER BY m.upload_date DESC
    ''').fetchall()
    
    # Get all evaluation data
    evaluations_data = db.execute('''
        SELECT e.*, m.cultural_reach, m.humor_type, m.estimated_year
        FROM evaluations e
        JOIN memes m ON e.meme_id = m.id
        ORDER BY e.evaluation_date DESC
    ''').fetchall()
    
    # Get user data (anonymized)
    users_data = db.execute('''
        SELECT country, research_interest, total_submissions, total_evaluations, 
               evaluation_accuracy, registration_date
        FROM users 
        WHERE is_active = 1
        ORDER BY total_submissions DESC
    ''').fetchall()
    
    # Convert to JSON for easy export
    memes_json = []
    for meme in memes_data:
        meme_dict = dict(meme)
        # Parse emotions JSON
        if meme_dict.get('emotions_conveyed'):
            try:
                meme_dict['emotions_conveyed'] = json.loads(meme_dict['emotions_conveyed'])
            except:
                meme_dict['emotions_conveyed'] = []
        # Remove sensitive data
        meme_dict.pop('contributor_email', None)
        if not current_app.config.get('DEVELOPMENT', False):
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

@bp.route('/reset_session')
def reset_session():
    """Reset current session (for testing)"""
    if not current_app.config.get('DEVELOPMENT', False):
        flash('This feature is only available in development mode.')
        return redirect(url_for('main.index'))
    
    session.clear()
    flash('Session reset! You can now start fresh.')
    return redirect(url_for('main.index'))

@bp.route('/test_session')
def test_session():
    app_session = AppSession(get_current_user(get_db()))
    return jsonify({
        'uploads': app_session.upload_count,
        'evals': app_session.eval_count,
        'name': app_session.name,
        'user_id': app_session.user_id,
        'session_id': app_session.session_id,
        'evaluation_accuracy': app_session.evaluation_accuracy
    })