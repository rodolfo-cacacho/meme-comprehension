# memeqa/__init__.py
from flask import Flask,render_template
import os
from datetime import datetime
from config import Config  # Your existing config.py


def create_app():
    """Application factory pattern"""
    app = Flask(__name__)
    
    app.config.from_object(Config)
    
    # Initialize database
    from memeqa.database import init_db, close_db
    app.teardown_appcontext(close_db)
    
    with app.app_context():
        init_db()
    
    # Create upload folder
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Register blueprints
    from memeqa.routes import main, auth, memes, evaluations
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp, url_prefix='/auth')
    app.register_blueprint(memes.bp, url_prefix='/memes')
    app.register_blueprint(evaluations.bp, url_prefix='/evaluate')

    # Register error handlers
    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return render_template('errors/500.html'), 500
    
    # Add context processors to make variables available in all templates
    @app.context_processor
    def inject_config():
        """Make config values available in all templates"""
        return {
            'eval_mems': app.config['EVAL_COUNT'],
            'memes_min': app.config['MIN_MEME_COUNT'],
            'development': app.config.get('DEVELOPMENT', False)
        }
    
    @app.context_processor
    def inject_user_data():
        """Make user data available in all templates"""
        from memeqa.database import get_db
        from memeqa.utils import get_current_user
        from flask import session
        import uuid
        
        # Get current user
        db = get_db()
        current_user = get_current_user(db)
        
        # Get evaluation count for the current session/user
        session_id = session.get('session_id', str(uuid.uuid4()))
        
        if current_user:
            eval_count_result = db.execute(
                'SELECT COUNT(*) as count FROM evaluations WHERE user_id = ?',
                (current_user['id'],)
            ).fetchone()
            eval_count = eval_count_result['count'] if eval_count_result else 0
        else:
            eval_count_result = db.execute(
                'SELECT COUNT(*) as count FROM evaluations WHERE session_id = ? AND user_id IS NULL',
                (session_id,)
            ).fetchone()
            eval_count = eval_count_result['count'] if eval_count_result else 0
        
        return {
            'current_user': current_user,
            'eval_count': eval_count,
            'get_user_evaluation_count': lambda: eval_count  # For templates that call it as function
        }
    
    # Add this context processor
    @app.context_processor
    def inject_app_info():
        """Make app info available to all templates"""
        try:
            # Get the modification time of the init file
            app_file = __file__
            mod_time = os.path.getmtime(app_file)
            last_updated = datetime.fromtimestamp(mod_time)
            
            return {
                'app_last_updated': last_updated,
                'app_version': '2.0 Enhanced'
            }
        except:
            return {
                'app_last_updated': datetime(2025, 1, 1),
                'app_version': '2.0 Enhanced'
            }


    return app