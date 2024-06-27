import os
import subprocess
import webbrowser
from flask import Flask, render_template, request, redirect, send_file, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime

from job import Job

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'  # Make sure this folder exists
app.config['PROCESSED_FOLDER'] = 'processed'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

@app.route('/', methods=['POST', 'GET'])
def index():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            return render_template('index.html', error='Username already exists', users=User.query.all())

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
        except:
            return 'There was an issue adding your task'
    
    users = User.query.all()
    return render_template('index.html', users=users)

@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        session.permanent = True
        if user and check_password_hash(user.password, password):
            token = jwt.encode({'user': user.username, 'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=30)}, app.config['SECRET_KEY'])
            session['token'] = token
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid username or password')
    
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    token = session.get('token')
    
    if not token:
        return redirect(url_for('login'))
    
    try:
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    except:
        return redirect(url_for('login'))
    
    return render_template('dashboard.html', username=data['user'], upload_error=None)

@app.route('/upload', methods=['POST'])
def upload_file():
    token = session.get('token')
    
    if not token:
        return redirect(url_for('login'))

    try:
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    except:
        return redirect(url_for('login'))

    if 'file' not in request.files:
        return render_template('dashboard.html', username=data['user'], upload_error='No file part')
    
    file = request.files['file']
    
    if file.filename == '':
        return render_template('dashboard.html', username=data['user'], upload_error='No selected file')

    num_mappers = request.form.get('num_mappers')
    num_reducers = request.form.get('num_reducers')

    if file and num_mappers and num_reducers:
        try:
            num_mappers = int(num_mappers)
            num_reducers = int(num_reducers)
        except ValueError:
            return render_template('dashboard.html', username=data['user'], upload_error='Mappers and reducers must be integers')

        filename = file.filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        file.save(file_path)

        # Read file content
        with open(file_path, 'r') as f:
            file_content = f.read()

        # Run your command here
        processed_filename = f"processed_{filename}"
        processed_file_path = os.path.join(app.config['PROCESSED_FOLDER'], processed_filename)
            
        if not os.path.exists(app.config['PROCESSED_FOLDER']):
            os.makedirs(app.config['PROCESSED_FOLDER'])
        
        print(file_path)
        print(filename)
        job = Job(file_path, filename, num_mappers, num_reducers)
        job_result = str(job.run())
        with open(processed_file_path, 'w') as processed_file:
            processed_file.write(job_result)

    return render_template('file_content.html', username=data['user'], file_content=job_result, filename=processed_filename)

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    file_path = os.path.join(app.config['PROCESSED_FOLDER'], filename)
    return send_file(file_path, as_attachment=True)

@app.route('/logout')
def logout():
    session.pop('token', None)
    return redirect(url_for('login'))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        webbrowser.open_new('http://localhost:5000/')
    app.run(debug=True)