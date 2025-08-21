import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration settings"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    GMAIL_USER = os.environ.get('GMAIL_USER')
    GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD')
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
    MIN_MEME_COUNT = 1
    EVAL_COUNT = 5
    
    # Environment detection - make sure these are uppercase
    ENV = os.environ.get('ENV', 'production')
    DEVELOPMENT = (ENV == 'development')
    DEBUG = (ENV == 'development')

    # Database configuration
    DATABASE_PATH = 'memes.db'