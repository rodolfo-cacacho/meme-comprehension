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
    platform_found TEXT NOT NULL,
    session_id TEXT,
    user_id INTEGER,
    
    -- Content Classification
    languages TEXT NOT NULL, -- JSON array of languages
    
    -- Humor & Emotional Analysis
    humor_type TEXT NOT NULL,
    emotions_conveyed TEXT NOT NULL, -- JSON array of emotions
    
    -- Context & References
    context_level TEXT NOT NULL, -- User's evaluation of context level
    
    -- Vote Counters
    likes INTEGER NOT NULL DEFAULT 0, -- Counter for meme likes

    -- Additional Data
    terms_agreement BOOLEAN NOT NULL DEFAULT 0,
    
    -- Metadata
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
);

-- Meme Descriptions table
CREATE TABLE IF NOT EXISTS meme_descriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meme_id INTEGER NOT NULL,
    description TEXT NOT NULL, -- Description content
    is_original BOOLEAN NOT NULL DEFAULT 0, -- 1 for original upload, 0 for edits
    user_id INTEGER, -- User who created/edited the description
    session_id TEXT, -- Session ID for anonymous users
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    likes INTEGER NOT NULL DEFAULT 0, -- Counter for description likes
    dislikes INTEGER NOT NULL DEFAULT 0, -- Counter for description dislikes
    FOREIGN KEY (meme_id) REFERENCES memes (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
);

-- Evaluations table
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id INTEGER,
    meme_id INTEGER NOT NULL,
    was_correct BOOLEAN, -- Whether the user correctly identified the meme's attributes
    evaluation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    evaluation_time_seconds INTEGER, -- Time taken to evaluate
    evaluated_humor_type TEXT, -- User's evaluation of humor type
    evaluated_emotions TEXT, -- User's evaluation of emotions (JSON array)
    evaluated_context_level TEXT NOT NULL, -- User's evaluation of context level
    matches_humor_type BOOLEAN, -- Whether evaluated humor matches original
    emotion_overlap_score REAL, -- Overlap score for emotions
    UNIQUE(meme_id, user_id), -- Ensure one evaluation per user per meme
    FOREIGN KEY (meme_id) REFERENCES memes (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- This is completely separate from evaluations
CREATE TABLE IF NOT EXISTS meme_likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meme_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    session_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(meme_id, user_id),  -- One like per registered user per meme
    FOREIGN KEY (meme_id) REFERENCES memes (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- This tracks votes on specific descriptions
CREATE TABLE IF NOT EXISTS description_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description_id INTEGER NOT NULL,
    meme_id INTEGER NOT NULL, -- Denormalized for easier queries
    user_id INTEGER,
    session_id TEXT NOT NULL,
    vote INTEGER CHECK (vote IN (1, -1, 0)), -- 1=like, -1=dislike, 0=neutral
    evaluation_time_seconds INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(description_id, user_id),  -- One evaluation per registered user per description
    UNIQUE(description_id, session_id), -- One evaluation per anonymous session per description
    FOREIGN KEY (description_id) REFERENCES meme_descriptions (id) ON DELETE CASCADE,
    FOREIGN KEY (meme_id) REFERENCES memes (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CHECK ((user_id IS NOT NULL) OR (session_id IS NOT NULL))
);

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    country TEXT NOT NULL,
    languages TEXT NOT NULL,
    birth_year INTEGER NOT NULL,
    affiliation TEXT,
    research_interest TEXT,
    notify_updates INTEGER DEFAULT 0,
    notify_milestones INTEGER DEFAULT 0,
    data_access_interest INTEGER DEFAULT 0,
    total_submissions INTEGER DEFAULT 0,
    total_evaluations INTEGER DEFAULT 0,
    total_descriptions INTEGER DEFAULT 0,
    evaluation_accuracy REAL DEFAULT 0.0,
    liked_memes INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
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
    FOREIGN KEY (meme_id) REFERENCES memes (id) ON DELETE CASCADE
);

-- User sessions table
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    user_id INTEGER,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    evaluations_completed INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
);

-- TRIGGERS

CREATE TRIGGER IF NOT EXISTS increment_meme_likes
AFTER INSERT ON meme_likes
BEGIN
    UPDATE memes
    SET likes = likes + 1
    WHERE id = NEW.meme_id;
END;

CREATE TRIGGER IF NOT EXISTS decrement_meme_likes
AFTER DELETE ON meme_likes
BEGIN
    UPDATE memes
    SET likes = likes - 1
    WHERE id = OLD.meme_id;
END;

-- Trigger to update like/dislike counters when a new evaluation is inserted
CREATE TRIGGER IF NOT EXISTS update_description_likes_on_insert
AFTER INSERT ON description_evaluations
FOR EACH ROW
BEGIN
    -- Increment likes if vote = 1
    UPDATE meme_descriptions
    SET likes = likes + 1
    WHERE id = NEW.description_id AND NEW.vote = 1;

    -- Increment dislikes if vote = -1
    UPDATE meme_descriptions
    SET dislikes = dislikes + 1
    WHERE id = NEW.description_id AND NEW.vote = -1;
END;

CREATE TRIGGER IF NOT EXISTS update_user_on_meme_insert
AFTER INSERT ON memes
FOR EACH ROW
WHEN NEW.user_id IS NOT NULL
BEGIN
    UPDATE users
    SET total_submissions = total_submissions + 1
    WHERE id = NEW.user_id;
END;

CREATE TRIGGER IF NOT EXISTS update_user_on_description_insert
AFTER INSERT ON meme_descriptions
FOR EACH ROW
WHEN NEW.user_id IS NOT NULL
BEGIN
    UPDATE users
    SET total_descriptions = total_descriptions + 1
    WHERE id = NEW.user_id;
END;

CREATE TRIGGER IF NOT EXISTS update_user_on_evaluation_insert
AFTER INSERT ON evaluations
FOR EACH ROW
WHEN NEW.user_id IS NOT NULL
BEGIN
    UPDATE users
    SET total_evaluations = total_evaluations + 1
    WHERE id = NEW.user_id;
END;

CREATE TRIGGER IF NOT EXISTS update_user_on_like_insert
AFTER INSERT ON meme_likes
FOR EACH ROW
WHEN NEW.user_id IS NOT NULL
BEGIN
    UPDATE users
    SET liked_memes = liked_memes + 1
    WHERE id = NEW.user_id;
END;

CREATE TRIGGER IF NOT EXISTS update_user_on_like_delete
AFTER DELETE ON meme_likes
FOR EACH ROW
WHEN OLD.user_id IS NOT NULL
BEGIN
    UPDATE users
    SET liked_memes = liked_memes - 1
    WHERE id = OLD.user_id;
END;