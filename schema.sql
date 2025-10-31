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
    uploader_session TEXT,
    uploader_user_id INTEGER,
    
    -- Content Classification
    meme_content TEXT NOT NULL,
    
    -- Humor & Emotional Analysis
    humor_type TEXT NOT NULL,
    emotions_conveyed TEXT NOT NULL, -- JSON array of emotions
    
    -- Context & References
    context_required TEXT NOT NULL,
    
    -- Vote Counters
    likes INTEGER NOT NULL DEFAULT 0, -- Counter for meme likes
    dislikes INTEGER NOT NULL DEFAULT 0, -- Counter for meme dislikes
    
    -- Additional Data
    terms_agreement BOOLEAN NOT NULL DEFAULT 0,
    
    -- Metadata
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (uploader_user_id) REFERENCES users (id) ON DELETE SET NULL
);

-- Meme Descriptions table
CREATE TABLE IF NOT EXISTS meme_descriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meme_id INTEGER NOT NULL,
    description TEXT NOT NULL, -- Description content
    is_original BOOLEAN NOT NULL DEFAULT 0, -- 1 for original upload, 0 for edits
    uploader_user_id INTEGER, -- User who created/edited the description
    uploader_session TEXT, -- Session ID for anonymous users
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    likes INTEGER NOT NULL DEFAULT 0, -- Counter for description likes
    dislikes INTEGER NOT NULL DEFAULT 0, -- Counter for description dislikes
    FOREIGN KEY (meme_id) REFERENCES memes (id) ON DELETE CASCADE,
    FOREIGN KEY (uploader_user_id) REFERENCES users (id) ON DELETE SET NULL
);

-- Evaluations table
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id INTEGER,
    meme_id INTEGER NOT NULL,
    description_id INTEGER, -- References the specific description evaluated (NULL if no description evaluated)
    meme_vote INTEGER CHECK (meme_vote IN (1, -1, NULL)), -- 1 for like, -1 for dislike, NULL if not voted
    description_vote INTEGER CHECK (description_vote IN (1, -1, NULL)), -- 1 for like, -1 for dislike, NULL if not voted or no description
    was_correct BOOLEAN, -- Whether the user correctly identified the meme's attributes
    confidence_level INTEGER DEFAULT 3 CHECK (confidence_level BETWEEN 1 AND 5), -- 1-5 confidence rating
    evaluation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    evaluation_time_seconds INTEGER, -- Time taken to evaluate
    evaluated_humor_type TEXT, -- User's evaluation of humor type
    evaluated_emotions TEXT, -- User's evaluation of emotions (JSON array)
    evaluated_context_level TEXT, -- User's evaluation of context level
    matches_humor_type BOOLEAN, -- Whether evaluated humor matches original
    emotion_overlap_score REAL, -- Overlap score for emotions
    UNIQUE(meme_id, user_id), -- Ensure one evaluation per user per meme
    FOREIGN KEY (meme_id) REFERENCES memes (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (description_id) REFERENCES meme_descriptions (id) ON DELETE SET NULL
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
    evaluation_accuracy REAL DEFAULT 0.0,
    is_active INTEGER DEFAULT 1,
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

-- Trigger to update meme likes count
CREATE TRIGGER IF NOT EXISTS update_meme_likes
AFTER INSERT ON evaluations
WHEN NEW.meme_vote = 1
BEGIN
    UPDATE memes
    SET likes = likes + 1
    WHERE id = NEW.meme_id;
END;

-- Trigger to update meme dislikes count
CREATE TRIGGER IF NOT EXISTS update_meme_dislikes
AFTER INSERT ON evaluations
WHEN NEW.meme_vote = -1
BEGIN
    UPDATE memes
    SET dislikes = dislikes + 1
    WHERE id = NEW.meme_id;
END;

-- Trigger to handle meme vote updates (e.g., changing from like to dislike)
CREATE TRIGGER IF NOT EXISTS update_meme_vote_change
AFTER UPDATE OF meme_vote ON evaluations
BEGIN
    -- If vote changed to like
    UPDATE memes
    SET likes = likes + 1,
        dislikes = CASE WHEN OLD.meme_vote = -1 THEN dislikes - 1 ELSE dislikes END
    WHERE id = NEW.meme_id AND NEW.meme_vote = 1;

    -- If vote changed to dislike
    UPDATE memes
    SET dislikes = dislikes + 1,
        likes = CASE WHEN OLD.meme_vote = 1 THEN likes - 1 ELSE likes END
    WHERE id = NEW.meme_id AND NEW.meme_vote = -1;

    -- If vote removed (set to NULL)
    UPDATE memes
    SET likes = CASE WHEN OLD.meme_vote = 1 THEN likes - 1 ELSE likes END,
        dislikes = CASE WHEN OLD.meme_vote = -1 THEN dislikes - 1 ELSE dislikes END
    WHERE id = NEW.meme_id AND NEW.meme_vote IS NULL;
END;

-- Trigger to handle deletion of meme evaluations
CREATE TRIGGER IF NOT EXISTS update_meme_vote_delete
AFTER DELETE ON evaluations
BEGIN
    UPDATE memes
    SET likes = CASE WHEN OLD.meme_vote = 1 THEN likes - 1 ELSE likes END,
        dislikes = CASE WHEN OLD.meme_vote = -1 THEN dislikes - 1 ELSE dislikes END
    WHERE id = OLD.meme_id;
END;

-- Trigger to update description likes count
CREATE TRIGGER IF NOT EXISTS update_description_likes
AFTER INSERT ON evaluations
WHEN NEW.description_vote = 1
BEGIN
    UPDATE meme_descriptions
    SET likes = likes + 1
    WHERE id = NEW.description_id;
END;

-- Trigger to update description dislikes count
CREATE TRIGGER IF NOT EXISTS update_description_dislikes
AFTER INSERT ON evaluations
WHEN NEW.description_vote = -1
BEGIN
    UPDATE meme_descriptions
    SET dislikes = dislikes + 1
    WHERE id = NEW.description_id;
END;

-- Trigger to handle description vote updates
CREATE TRIGGER IF NOT EXISTS update_description_vote_change
AFTER UPDATE OF description_vote ON evaluations
BEGIN
    -- If vote changed to like
    UPDATE meme_descriptions
    SET likes = likes + 1,
        dislikes = CASE WHEN OLD.description_vote = -1 THEN dislikes - 1 ELSE dislikes END
    WHERE id = NEW.description_id AND NEW.description_vote = 1;

    -- If vote changed to dislike
    UPDATE meme_descriptions
    SET dislikes = dislikes + 1,
        likes = CASE WHEN OLD.description_vote = 1 THEN likes - 1 ELSE likes END
    WHERE id = NEW.description_id AND NEW.description_vote = -1;

    -- If vote removed (set to NULL)
    UPDATE meme_descriptions
    SET likes = CASE WHEN OLD.description_vote = 1 THEN likes - 1 ELSE likes END,
        dislikes = CASE WHEN OLD.description_vote = -1 THEN dislikes - 1 ELSE dislikes END
    WHERE id = NEW.description_id AND NEW.description_vote IS NULL;
END;

-- Trigger to handle deletion of description evaluations
CREATE TRIGGER IF NOT EXISTS update_description_vote_delete
AFTER DELETE ON evaluations
BEGIN
    UPDATE meme_descriptions
    SET likes = CASE WHEN OLD.description_vote = 1 THEN likes - 1 ELSE likes END,
        dislikes = CASE WHEN OLD.description_vote = -1 THEN dislikes - 1 ELSE dislikes END
    WHERE id = OLD.description_id;
END;