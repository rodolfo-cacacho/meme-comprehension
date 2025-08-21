-- MemeQA Database Schema

-- Memes table
CREATE TABLE IF NOT EXISTS memes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    
    -- Contributor Information
    contributor_name TEXT,
    contributor_email TEXT,
    contributor_country TEXT NOT NULL,
    meme_origin_country TEXT,
    platform_found TEXT NOT NULL,
    uploader_session TEXT,
    uploader_user_id INTEGER,
    
    -- Content Classification
    meme_content TEXT NOT NULL,
    meme_template TEXT,
    estimated_year TEXT NOT NULL,
    cultural_reach TEXT NOT NULL,
    niche_community TEXT,
    
    -- Humor & Emotional Analysis
    humor_explanation TEXT NOT NULL,
    humor_type TEXT NOT NULL,
    emotions_conveyed TEXT NOT NULL,
    
    -- Context & References
    cultural_references TEXT,
    context_required TEXT NOT NULL,
    age_group_target TEXT,
    
    -- AI Training Descriptions
    -- meme_description TEXT NOT NULL,
    -- correct_description INTEGER,
    
    -- Additional Data
    additional_notes TEXT,
    terms_agreement BOOLEAN NOT NULL DEFAULT 0,
    
    -- Metadata
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (uploader_user_id) REFERENCES users (id)
);

-- Evaluations table
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id INTEGER,
    meme_id INTEGER NOT NULL,
    chosen_description INTEGER NOT NULL,
    was_correct BOOLEAN,
    confidence_level INTEGER DEFAULT 3,
    evaluation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    evaluation_time_seconds INTEGER,
    evaluated_humor_type TEXT,
    evaluated_emotions TEXT,
    evaluated_context_level TEXT,
    matches_humor_type BOOLEAN,
    emotion_overlap_score REAL,
    FOREIGN KEY (meme_id) REFERENCES memes (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    country TEXT,
    affiliation TEXT,
    research_interest TEXT,
    
    -- Notification preferences
    notify_updates BOOLEAN DEFAULT 1,
    notify_milestones BOOLEAN DEFAULT 1,
    data_access_interest BOOLEAN DEFAULT 0,
    
    -- Statistics
    total_submissions INTEGER DEFAULT 0,
    total_evaluations INTEGER DEFAULT 0,
    evaluation_accuracy REAL DEFAULT 0.0,
    
    -- Metadata
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

-- Analytics table
CREATE TABLE IF NOT EXISTS meme_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meme_id INTEGER NOT NULL,
    total_evaluations INTEGER DEFAULT 0,
    correct_identifications INTEGER DEFAULT 0,
    accuracy_rate REAL DEFAULT 0.0,
    avg_evaluation_time REAL DEFAULT 0.0,
    avg_confidence_level REAL DEFAULT 0.0,
    difficulty_score REAL DEFAULT 0.0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (meme_id) REFERENCES memes (id)
);

-- User sessions table
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    user_id INTEGER,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    evaluations_completed INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users (id)
);