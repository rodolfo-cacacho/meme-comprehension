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
    # Generate file extension accept string
    ACCEPT_FILE_TYPES = '.' + ',.'.join(ALLOWED_EXTENSIONS)

    MIN_MEME_COUNT = 0
    EVAL_COUNT = 100
    MAX_EVAL =5
    MAX_UPLOAD =1
    ANON_MAX_EVAL = 5
    ANON_MAX_UPLOAD = 1
    REG_MAX_EVAL = 10000  # Unlimited
    REG_MAX_UPLOAD = 10000
    PROMPT_EVAL_EVERY = 10  # should_prompt_upload
    PROMPT_UPLOAD_EVERY = 5  # should_prompt_evaluate
    
    # Environment detection - make sure these are uppercase
    ENV = os.environ.get('ENV', 'production')
    DEVELOPMENT = (ENV == 'development')
    DEBUG = (ENV == 'development')

    # Database configuration
    DATABASE_PATH = 'memes.db'

    EMOTIONS_TYPES = [
    {
        'emotion': 'Joy',
        'description': 'The meme makes me feel happy, joyful, amused, or cheerful',
        'emoji': '😊'
    },
    {
        'emotion': 'Trust',
        'description': 'The meme evokes feelings of acceptance, reassurance, or connection with others',
        'emoji': '🤗'
    },
    {
        'emotion': 'Fear',
        'description': 'The meme causes feelings of worry, anxiety, unease, or apprehension',
        'emoji': '😰'
    },
    {
        'emotion': 'Surprise',
        'description': 'The meme is shocking, unexpected, or catches me off guard',
        'emoji': '😲'
    },
    {
        'emotion': 'Sadness',
        'description': 'The meme evokes feelings of melancholy, disappointment, or emotional heaviness',
        'emoji': '😢'
    },
    {
        'emotion': 'Disgust',
        'description': 'The meme triggers feelings of revulsion, distaste, or strong disapproval',
        'emoji': '🤢'
    },
    {
        'emotion': 'Anger',
        'description': 'The meme evokes feelings of frustration, annoyance, irritation, or outrage',
        'emoji': '😤'
    },
    {
        'emotion': 'Anticipation',
        'description': 'The meme creates feelings of expectation, interest, or excitement about what comes next',
        'emoji': '🤔'
    }
    ]

    # EMOTIONS_TYPES = [
    #     {'emotion': 'Joy', 'description': 'The meme makes me feel happy, joyful, or amused.', 'emoji': '😊'},
    #     {'emotion': 'Frustration', 'description': 'The meme evokes feelings of annoyance or irritation.', 'emoji': '😤'},
    #     {'emotion': 'Confusion', 'description': 'The meme is puzzling or hard to understand.', 'emoji': '😕'},
    #     {'emotion': 'Pride', 'description': 'The meme instills a sense of pride or accomplishment.', 'emoji': '😎'},
    #     {'emotion': 'Nostalgia', 'description': 'The meme brings back fond memories.', 'emoji': '🥺'},
    #     {'emotion': 'Anxiety', 'description': 'The meme causes feelings of worry or unease.', 'emoji': '😰'},
    #     {'emotion': 'Relief', 'description': 'The meme evokes a sense of relief or calm.', 'emoji': '😌'},
    #     {'emotion': 'Surprise', 'description': 'The meme is shocking or unexpected.', 'emoji': '😲'}
    # ]

    HUMOR_TYPES = [
        {
            'type': 'Irony/Sarcasm',
            'description': 'The meme uses irony or sarcasm to convey humor, saying one thing but meaning another or using mocking tone',
            'emoji': '😏'
        },
        {
            'type': 'Relatability',
            'description': 'The meme reflects relatable everyday experiences, situations, or feelings that resonate with common human experiences',
            'emoji': '🤝'
        },
        {
            'type': 'Absurd/Random',
            'description': 'The meme is humorous due to its absurdity, randomness, or surreal illogical elements that defy expectations',
            'emoji': '🤪'
        },
        {
            'type': 'Wordplay/Visual',
            'description': 'The humor comes from clever wordplay, puns, visual elements, image composition, or creative juxtaposition',
            'emoji': '😜🖼️'
        },
        {
            'type': 'Dark/Edgy',
            'description': 'The meme uses dark, edgy, or provocative humor that touches on taboo, controversial, or sensitive topics',
            'emoji': '😈'
        },
        {
            'type': 'Social Commentary',
            'description': 'The meme comments on societal issues, cultural norms, politics, or social behaviors with critical or observational humor',
            'emoji': '📣'
        },
        {
            'type': 'Wholesome',
            'description': 'The meme conveys positive, heartwarming, uplifting feelings that inspire joy, kindness, or emotional warmth',
            'emoji': '🥰'
        },
        {
            'type': 'Self-Deprecating',
            'description': 'The meme makes fun of oneself, highlighting personal flaws, failures, or embarrassing situations in a humorous way',
            'emoji': '😅'
        },
        {
            'type': 'Not Humorous',
            'description': 'The meme is not intended to be funny; it is informational, serious, or earnest',
            'emoji': '😐'
        }
    ]

    # HUMOR_TYPES = [
    #     {'type': 'Irony/Sarcasm', 'description': 'The meme uses irony or sarcasm to convey humor.', 'emoji': '😏'},
    #     {'type': 'Relatability', 'description': 'The meme reflects relatable everyday experiences.', 'emoji': '🤝'},
    #     {'type': 'Absurd/Random', 'description': 'The meme is humorous due to its absurdity or randomness.', 'emoji': '🤪'},
    #     {'type': 'Wordplay/Puns', 'description': 'The meme uses clever wordplay or puns.', 'emoji': '😜'},
    #     {'type': 'Visual Humor', 'description': 'The humor comes from visual elements.', 'emoji': '🖼️'},
    #     {'type': 'Dark Humor', 'description': 'The meme uses dark or edgy humor.', 'emoji': '😈'},
    #     {'type': 'Self-deprecating', 'description': 'The meme pokes fun at oneself.', 'emoji': '😅'},
    #     {'type': 'Social Commentary', 'description': 'The meme comments on societal issues.', 'emoji': '📣'},
    #     {'type': 'Pop Culture Reference', 'description': 'The meme references popular culture.', 'emoji': '🎬'},
    #     {'type': 'Wholesome', 'description': 'The meme conveys positive, heartwarming feelings.', 'emoji': '🥰'},
    #     {'type': 'Not Humorous', 'description': 'The meme is not intended to be funny.', 'emoji': '😐'}
    # ]

    TIME_RANGE_OPTIONS = [
        '2021-2025', '2016-2020','2010-2015', 'Pre-2010','Unknown'
    ]

    PLATFORM_OPTIONS = [
        'Reddit', 'Instagram', 'Twitter/X', 'TikTok', 'Discord', '9GAG', 'Imgur', 'WhatsApp', 'Telegram', 'Facebook', 'Tumblr', '4chan', 'Original Creation', 'Other', 'Unknown'
    ]

    COUNTRIES_MEMES = [
        'Unknown', 'United States', 'Germany', 'United Kingdom', 'France', 'Spain', 'Italy', 'Canada', 'Australia', 'Japan', 'South Korea', 'China',
        'India', 'Brazil', 'Mexico', 'Russia', 'Global/International', 'Other'
    ]

    COUNTRIES = [
        'United States', 'Germany', 'United Kingdom', 'France', 'Spain', 'Italy', 'Canada', 'Australia', 'Japan', 'South Korea', 'China',
        'India', 'Brazil', 'Mexico', 'Russia','Other'
    ]

    CULTURAL_REACH_OPTIONS = {
        'Global':'Global (understood worldwide)',
        'Western':'Western Culture',
        'Regional':'Regional (specific continent/region)',
        'National':'National (country-specific)',
        'Local':'Local (city/community specific)',
        'Niche Community':'Niche Community'
    }

    CONTEXT_LEVELS = {
        'None':'None (self-explanatory)',
        'Basic':'Basic Internet Knowledge',
        'Pop Culture':'Pop Culture Awareness',
        'Current/Past Events':'Current/Past Events Knowledge',
        'Specialized Knowledge':'Specialized Knowledge',
        'Deep Context':'Deep Context (very obscure references)'
    }

    # Load countries from txt file
    try:
        with open('memeqa/static/countries.txt', 'r') as f:
            COUNTRIES = sorted([line.strip() for line in f if line.strip()])
    except FileNotFoundError:
        COUNTRIES = []
        print("Warning: countries.txt not found, country list empty.")

    # Load languages from txt file
    try:
        with open('memeqa/static/languages.txt', 'r') as f:
            LANGUAGES = sorted([line.strip() for line in f if line.strip()])
    except FileNotFoundError:
        LANGUAGES = []
        print("Warning: languages.txt not found, language list empty.")