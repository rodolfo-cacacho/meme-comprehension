# MemeQA: Crowd-sourced Meme Understanding Benchmark

A Flask-based web application for collecting crowd-sourced evaluations of meme descriptions to create a benchmark dataset for testing Vision-Language Models (VLLMs) in meme comprehension and humor understanding.

## 🎯 Project Overview

**MemeQA** is a research project developed by **THWS (Technische Hochschule Würzburg-Schweinfurt)** and **CAIRO (Center for AI and Robotics)** to evaluate AI systems' ability to understand internet memes, cultural references, and humor.

### Research Goals
- Evaluate VLLM meme comprehension capabilities
- Benchmark humor understanding in AI systems
- Create diverse cultural context dataset
- Enable explainable meme analysis

## 🚀 Features

- **Crowd-sourced Evaluation System**: Users evaluate memes by choosing the best description from 4 options
- **Quality Control**: Users must evaluate 10 memes before uploading their own
- **Bootstrap Mode**: Early users can upload without evaluation requirements to build initial dataset
- **Session Tracking**: Prevents duplicate evaluations and tracks user progress
- **Multi-description Upload**: Each meme requires 4 different descriptions for comprehensive evaluation
- **Clean Web Interface**: Bootstrap-based responsive UI
- **Statistics Dashboard**: Real-time stats on contributions and dataset growth

## 🛠 Installation

### Prerequisites
- Python 3.7+
- Flask
- SQLite (included with Python)

### Setup
1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd memeqa
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python app.py
   ```

4. **Access the application**
   - Open http://127.0.0.1:5000 in your browser

## 📁 Project Structure

```
memeqa/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── templates/            # HTML templates
│   ├── base.html         # Base template
│   ├── index.html        # Landing page
│   ├── evaluate.html     # Meme evaluation interface
│   ├── upload.html       # Meme upload form
│   ├── gallery.html      # Browse all memes
│   └── stats.html        # Statistics dashboard
├── uploads/              # Uploaded meme files (auto-created)
└── memes.db             # SQLite database (auto-created)
```

## 🎮 How It Works

### User Workflow
1. **Landing Page**: Users see project introduction and progress tracking
2. **Evaluation Phase**: Choose best description from 4 randomized options for 10 different memes
3. **Upload Phase**: After completing evaluations, upload own meme with 4 descriptions
4. **Quality Assurance**: System prevents re-evaluation and tracks contributions

### Bootstrap Mode
- When fewer than 10 memes exist, users can upload without evaluation requirements
- Solves cold-start problem for initial dataset building
- Automatically switches to normal evaluation mode once sufficient content exists

## 🗄 Database Schema

### Memes Table
- **id**: Primary key
- **filename**: Unique generated filename
- **original_filename**: User's original filename
- **description_1-4**: Four different descriptions
- **upload_date**: Timestamp
- **uploader_session**: Session tracking

### Evaluations Table
- **id**: Primary key
- **session_id**: User session identifier
- **meme_id**: Reference to evaluated meme
- **chosen_description**: Selected description (1-4)
- **evaluation_date**: Timestamp

## 🔧 Configuration

### Environment Modes
- **Development**: Shows reset session functionality for testing
- **Production**: Hides debug features, optimized for deployment

### File Upload Settings
- **Supported formats**: PNG, JPG, JPEG, GIF
- **Maximum file size**: 16MB
- **Storage**: Local filesystem with unique filenames

## 📊 Applications

- **Social media content moderation**
- **Cultural trend analysis**
- **Humor-aware AI assistants**
- **Digital literacy tools**
- **VLLM benchmarking research**

## 🚀 Deployment

For production deployment:
1. Set `FLASK_ENV=production`
2. Change `SECRET_KEY` to a secure random value
3. Configure proper web server (nginx + gunicorn recommended)
4. Set up database backups
5. Implement proper logging and monitoring

## 📝 Contributing

This is a research project collecting data for academic purposes. Contributors help build a valuable dataset for advancing AI understanding of visual humor and cultural context.

## 📄 License

Apache License 2.0

## 🏛 Institutions

- **THWS** - Technische Hochschule Würzburg-Schweinfurt
- **CAIRO** - Center for AI and Robotics


*This project is part of ongoing research in Vision-Language Model evaluation and cultural AI understanding.*
