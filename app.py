from flask import Flask, render_template, request, jsonify
import re
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from PyPDF2 import PdfReader
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# Load secrets from environment variables
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

def preprocess_text(text):
    text = re.sub('http\S+\s*', ' ', text)
    text = re.sub('RT|cc', ' ', text)
    text = re.sub('#\S+', '', text)
    text = re.sub('@\S+', '  ', text)
    text = re.sub('[%s]' % re.escape("""!"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"""), ' ', text)
    text = re.sub(r'[^\x00-\x7f]', r' ', text)
    text = re.sub('\s+', ' ', text)
    return text.lower()

def extract_text_from_pdf(pdf_file):
    try:
        reader = PdfReader(pdf_file)
        text = ''
        for page in reader.pages:
            text += page.extract_text()
        return text
    except Exception:
        return ''

def get_keyword_gap(resume_text, jd_text):
    # JD ke words jo resume mein nahi hain
    stop_words = {'and', 'the', 'is', 'in', 'to', 'with', 'for', 'a', 'of', 'on', 'at', 'an'}
    jd_words = set(re.findall(r'\w+', jd_text.lower()))
    resume_words = set(re.findall(r'\w+', resume_text.lower()))
    
    missing = jd_words - resume_words - stop_words
    return list(missing)[:10] # Top 10 missing words

@app.route('/templates')
def templates():
    return render_template('templates.html')

# Database Configuration
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)

# User Model (Database Table)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

# Create Database Tables
with app.app_context():
    db.create_all()

# --- ROUTES ---

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_pw)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
        except:
            return "Username already exists!"
            
    return render_template('auth.html', mode='signup')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('index'))
        else:
            return "Invalid Login!"
            
    return render_template('auth.html', mode='login')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Protected Index Route (Sirf login ke baad dikhega)
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session['username'])

@app.route('/check_score', methods=['POST'])
def check_score():
    job_description = request.form.get('job_description', '')
    resume_text = request.form.get('resume_text', '')

    if 'resume_file' in request.files:
        resume_file = request.files['resume_file']
        if resume_file and resume_file.filename.endswith('.pdf'):
            resume_text = extract_text_from_pdf(resume_file)

    # Core logic
    clean_jd = preprocess_text(job_description)
    clean_resume = preprocess_text(resume_text)

    # ATS Score
    tfidf = TfidfVectorizer(stop_words='english')
    tfidf_matrix = tfidf.fit_transform([clean_resume, clean_jd])
    cosine_sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])
    ats_score = round(cosine_sim[0][0] * 100, 2)

    # Keyword Gap
    missing_keywords = get_keyword_gap(clean_resume, clean_jd)

    # Dynamic Feedback
    if ats_score >= 80:
        feedback = "Excellent! Your resume is highly optimized for this role."
    elif ats_score >= 50:
        feedback = "Good, but you're missing some key industry terms. Check the Keyword Gap."
    else:
        feedback = "High Risk: Your resume doesn't match the JD requirements well."

    return jsonify({
        "score": ats_score,
        "missing": missing_keywords,
        "feedback": feedback
    })

if __name__ == '__main__':
    app.run(debug=True)
