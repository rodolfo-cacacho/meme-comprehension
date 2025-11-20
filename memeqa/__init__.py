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
            'max_eval_anon': app.config['MAX_EVAL'],
            'max_upload_anon': app.config['MAX_UPLOAD'],
            'eval_mems': app.config['EVAL_COUNT'],
            'memes_min': app.config['MIN_MEME_COUNT'],
            'development': app.config.get('DEVELOPMENT', False)
        }

    @app.context_processor
    def inject_session_data():
        from memeqa.utils import AppSession
        from memeqa.utils import get_current_user
        from memeqa.database import get_db

        app_session = AppSession(get_current_user(get_db()))
        return {
            'app_session': app_session
        }
  
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