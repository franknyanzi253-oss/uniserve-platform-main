import os

# Load environment variables from .env file if it exists
if os.path.exists('.env'):
    with open('.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip()

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import re
import time
from datetime import datetime
from functools import wraps
from sqlalchemy import text
from flask import send_from_directory
from flask_socketio import SocketIO, emit, join_room
import urllib.request
import json
import secrets
import csv
import io

app = Flask(__name__)

# Google Client ID Configuration
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', '')

@app.context_processor
def inject_google_client_id():
    return dict(google_client_id=app.config['GOOGLE_CLIENT_ID'])

def verify_google_token(id_token):
    try:
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            if 'email' in data:
                return data
    except Exception as e:
        print("Google token verification failed:", e)
    return None

# Initialize SocketIO: force safe backend on Render, prefer eventlet locally
if os.environ.get('RENDER'):
    async_mode = 'threading'
else:
    async_mode = None
    try:
        import eventlet
        # Test if it actually works to import
        import eventlet.convenience
        async_mode = 'eventlet'
    except Exception as e:
        print('Eventlet unavailable or incompatible, falling back to threading:', e)
        async_mode = 'threading'

try:
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)
except Exception as e:
    print('SocketIO initialization failed with async_mode', async_mode, e)
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')


@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        join_room(f"user_{session['user_id']}")

# Serve Service Worker from the root
@app.route('/sw.js')
def serve_sw():
    return send_from_directory('.', 'sw.js', mimetype='application/javascript')

# Configuration - Different for development vs production
if os.environ.get('RENDER'):  # Render.com
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-secret-key')
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise RuntimeError('DATABASE_URL is required when RENDER=true')
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url.replace('postgres://', 'postgresql://')
    DEBUG = False
else:  # Local development
    app.config['SECRET_KEY'] = 'uniserve-secret-key-2024'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
    DEBUG = True

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
app.config['UPLOAD_FOLDER'] = 'static/uploads/profile_pictures'
app.config['UPLOAD_FOLDER_DOCS'] = 'static/uploads/documents'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['ALLOWED_DOC_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'pdf'}

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER_DOCS'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def allowed_doc_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_DOC_EXTENSIONS']

db = SQLAlchemy(app)

# Database Models (Keep all your existing models exactly as they are)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    profile_picture = db.Column(db.String(200), nullable=True)
    student_id_document = db.Column(db.String(200), nullable=True)
    verification_status = db.Column(db.String(20), default='unverified')
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    services = db.relationship('Service', backref='provider', lazy=True)
    reviews_given = db.relationship('Review', foreign_keys='Review.reviewer_id', backref='reviewer', lazy=True)
    reviews_received = db.relationship('Review', foreign_keys='Review.reviewee_id', backref='reviewee', lazy=True)

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.String(50), nullable=True)
    location = db.Column(db.String(100), nullable=False)
    contact_info = db.Column(db.String(100), nullable=False)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Foreign Keys
    provider_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    requests = db.relationship('ServiceRequest', backref='service', lazy=True)

class ServiceRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)
    seeker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    seeker = db.relationship('User', foreign_keys=[seeker_id], backref='service_requests')

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    review_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reviewee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    
    # Relationships
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')

# Ensure tables are created automatically on import
with app.app_context():
    db.create_all()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Admin access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Routes (Keep all your existing routes exactly as they are)
@app.route('/')
def index():
    services = Service.query.filter_by(is_active=True).order_by(Service.created_date.desc()).limit(6).all()
    return render_template('index.html', services=services)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        user_type = request.form['user_type']
        
        # Validate email format
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
            flash('Please use a valid email address.', 'danger')
            return redirect(url_for('register'))
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered. Please login.', 'danger')
            return redirect(url_for('login'))
        
        # Create new user
        hashed_password = generate_password_hash(password)
        new_user = User(
            name=name, 
            email=email, 
            password=hashed_password, 
            user_type=user_type
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            # Auto-promote admin via environment variable
            admin_email = os.environ.get('ADMIN_EMAIL')
            if admin_email and user.email.lower() == admin_email.lower() and not getattr(user, 'is_admin', False):
                user.is_admin = True
                db.session.commit()
                
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_type'] = user.user_type
            session['is_admin'] = getattr(user, 'is_admin', False)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/api/google-login', methods=['POST'])
def google_login():
    data = request.json or {}
    token = data.get('id_token')
    is_mock = data.get('is_mock', False)
    mock_email = data.get('mock_email')
    mock_name = data.get('mock_name', 'Google User')
    
    user_info = None
    if is_mock:
        if not mock_email or not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', mock_email):
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400
        user_info = {
            'email': mock_email,
            'name': mock_name,
            'picture': None
        }
    elif token:
        user_info = verify_google_token(token)
        if not user_info:
            return jsonify({'success': False, 'message': 'Invalid Google token'}), 400
    else:
        return jsonify({'success': False, 'message': 'No authentication data provided'}), 400
        
    email = user_info['email'].lower()
    name = user_info['name']
    picture = user_info.get('picture')
    
    user = User.query.filter_by(email=email).first()
    if user:
        session['user_id'] = user.id
        session['user_name'] = user.name
        session['user_type'] = user.user_type
        session['is_admin'] = getattr(user, 'is_admin', False)
        
        if not user.profile_picture and picture:
            user.profile_picture = picture
            db.session.commit()
            
        flash(f'Welcome back, {user.name}!', 'success')
        return jsonify({'success': True, 'redirect_url': url_for('dashboard')})
    else:
        session['google_register_email'] = email
        session['google_register_name'] = name
        session['google_register_picture'] = picture
        return jsonify({'success': True, 'redirect_url': url_for('complete_google_registration')})

@app.route('/complete-google-registration', methods=['GET', 'POST'])
def complete_google_registration():
    if 'google_register_email' not in session:
        flash('Session expired or invalid access.', 'danger')
        return redirect(url_for('register'))
        
    email = session['google_register_email']
    name = session['google_register_name']
    
    if request.method == 'POST':
        user_type = request.form.get('user_type')
        if user_type not in ['seeker', 'provider']:
            flash('Please select a valid role.', 'danger')
            return render_template('complete_google_registration.html', name=name, email=email)
            
        random_password = secrets.token_hex(16)
        hashed_password = generate_password_hash(random_password)
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            user = existing_user
        else:
            is_admin = False
            admin_email = os.environ.get('ADMIN_EMAIL')
            if admin_email and email.lower() == admin_email.lower():
                is_admin = True
                
            user = User(
                name=name,
                email=email,
                password=hashed_password,
                user_type=user_type,
                profile_picture=session.get('google_register_picture'),
                is_admin=is_admin
            )
            db.session.add(user)
            db.session.commit()
            
        session.pop('google_register_email', None)
        session.pop('google_register_name', None)
        session.pop('google_register_picture', None)
        
        session['user_id'] = user.id
        session['user_name'] = user.name
        session['user_type'] = user.user_type
        session['is_admin'] = getattr(user, 'is_admin', False)
        
        flash('Registration completed successfully! Welcome to UniServe.', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('complete_google_registration.html', name=name, email=email)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    if user.user_type == 'provider':
        services = Service.query.filter_by(provider_id=user.id).all()
        return render_template('dashboard.html', user=user, services=services)
    else:
        requests = ServiceRequest.query.filter_by(seeker_id=user.id).all()
        return render_template('dashboard.html', user=user, requests=requests)

@app.route('/services')
def services():
    category = request.args.get('category', '')
    search = request.args.get('search', '')
    
    query = Service.query.filter_by(is_active=True)
    
    if category:
        query = query.filter_by(category=category)
    
    if search:
        query = query.filter(Service.title.contains(search) | Service.description.contains(search))
    
    services = query.order_by(Service.created_date.desc()).all()
    categories = db.session.query(Service.category).distinct().all()
    
    return render_template('services.html', services=services, categories=categories)

@app.route('/add_service', methods=['GET', 'POST'])
def add_service():
    if 'user_id' not in session or session['user_type'] != 'provider':
        flash('Only service providers can add services.', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        price = request.form['price']
        location = request.form['location']
        contact_info = request.form['contact_info']
        
        new_service = Service(
            title=title,
            description=description,
            category=category,
            price=price,
            location=location,
            contact_info=contact_info,
            provider_id=session['user_id']
        )
        
        db.session.add(new_service)
        db.session.commit()
        
        flash('Service added successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('add_service.html')

@app.route('/request_service', methods=['POST'])
def request_service():
    if 'user_id' not in session:
        flash('Please login to request services.', 'danger')
        return redirect(url_for('login'))
    
    service_id = request.form['service_id']
    message = request.form['message']
    
    service = Service.query.get(service_id)
    if service and service.provider_id == session['user_id']:
        flash('You cannot request your own service.', 'warning')
        return redirect(url_for('dashboard'))
    
    new_request = ServiceRequest(
        service_id=service_id,
        seeker_id=session['user_id'],
        message=message
    )
    
    db.session.add(new_request)
    db.session.commit()
    
    socketio.emit('notification_ping', {}, room=f"user_{service.provider_id}")
    
    flash('Service request sent successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/profile/<int:user_id>')
def profile(user_id):
    user = User.query.get_or_404(user_id)
    reviews = Review.query.filter_by(reviewee_id=user_id).all()
    
    avg_rating = 0
    if reviews:
        avg_rating = sum([review.rating for review in reviews]) / len(reviews)
        
    seeker_requests = []
    if user.user_type == 'seeker':
        seeker_requests = ServiceRequest.query.filter_by(seeker_id=user.id).order_by(ServiceRequest.request_date.desc()).all()
        
    can_message = False
    if 'user_id' in session:
        current_user_id = session['user_id']
        is_admin = session.get('is_admin', False)
        if current_user_id == user.id or is_admin:
            can_message = True
        else:
            accepted_request = ServiceRequest.query.join(Service).filter(
                ((ServiceRequest.seeker_id == current_user_id) & (Service.provider_id == user.id)) |
                ((ServiceRequest.seeker_id == user.id) & (Service.provider_id == current_user_id))
            ).filter(ServiceRequest.status.in_(['accepted', 'completed'])).first()
            if accepted_request:
                can_message = True
    
    return render_template('profile.html', user=user, reviews=reviews, avg_rating=avg_rating, seeker_requests=seeker_requests, can_message=can_message)

# Profile Picture Routes
@app.route('/upload_profile_picture', methods=['POST'])
def upload_profile_picture():
    if 'user_id' not in session:
        flash('Please login to upload profile picture.', 'danger')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    if 'profile_picture' not in request.files:
        flash('No file selected.', 'danger')
        return redirect(url_for('profile', user_id=user.id))
    
    file = request.files['profile_picture']
    
    if file.filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('profile', user_id=user.id))
    
    if file and allowed_file(file.filename):
        if user.profile_picture:
            old_picture_path = os.path.join(app.config['UPLOAD_FOLDER'], user.profile_picture)
            if os.path.exists(old_picture_path):
                os.remove(old_picture_path)
        
        filename = secure_filename(file.filename)
        unique_filename = f"user_{user.id}_{int(time.time())}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        file.save(file_path)
        user.profile_picture = unique_filename
        db.session.commit()
        
        flash('Profile picture updated successfully!', 'success')
    else:
        flash('Invalid file type. Please upload PNG, JPG, JPEG, or GIF files only.', 'danger')
    
    return redirect(url_for('profile', user_id=user.id))

@app.route('/remove_profile_picture', methods=['POST'])
def remove_profile_picture():
    if 'user_id' not in session:
        flash('Please login to remove profile picture.', 'danger')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    if user.profile_picture:
        picture_path = os.path.join(app.config['UPLOAD_FOLDER'], user.profile_picture)
        if os.path.exists(picture_path):
            os.remove(picture_path)
        
        user.profile_picture = None
        db.session.commit()
        flash('Profile picture removed successfully!', 'success')
    else:
        flash('No profile picture to remove.', 'info')
    
    return redirect(url_for('profile', user_id=user.id))

@app.route('/upload_verification_id', methods=['POST'])
def upload_verification_id():
    if 'user_id' not in session:
        flash('Please login to upload verification document.', 'danger')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    if user.user_type != 'provider':
        flash('Only providers can be verified.', 'danger')
        return redirect(url_for('profile', user_id=user.id))
        
    if 'verification_document' not in request.files:
        flash('No file selected.', 'danger')
        return redirect(url_for('profile', user_id=user.id))
    
    file = request.files['verification_document']
    
    if file.filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('profile', user_id=user.id))
    
    if file and allowed_doc_file(file.filename):
        if user.student_id_document:
            old_doc_path = os.path.join(app.config['UPLOAD_FOLDER_DOCS'], user.student_id_document)
            if os.path.exists(old_doc_path):
                os.remove(old_doc_path)
        
        filename = secure_filename(file.filename)
        unique_filename = f"id_{user.id}_{int(time.time())}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER_DOCS'], unique_filename)
        
        file.save(file_path)
        user.student_id_document = unique_filename
        user.verification_status = 'pending'
        db.session.commit()
        
        flash('Student ID submitted for verification successfully!', 'success')
    else:
        flash('Invalid file type. Please upload PDF, PNG, JPG, or JPEG files only.', 'danger')
    
    return redirect(url_for('profile', user_id=user.id))

# Messaging Routes
@app.route('/messages')
def messages():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    sent_conversations = db.session.query(Message.receiver_id).filter_by(sender_id=user_id).distinct()
    received_conversations = db.session.query(Message.sender_id).filter_by(receiver_id=user_id).distinct()
    
    all_conversation_ids = set([id[0] for id in sent_conversations] + [id[0] for id in received_conversations])
    
    conversations = []
    for conv_id in all_conversation_ids:
        other_user = User.query.get(conv_id)
        last_message = Message.query.filter(
            ((Message.sender_id == user_id) & (Message.receiver_id == conv_id)) |
            ((Message.sender_id == conv_id) & (Message.receiver_id == user_id))
        ).order_by(Message.timestamp.desc()).first()
        
        unread_count = Message.query.filter_by(sender_id=conv_id, receiver_id=user_id, is_read=False).count()
        
        conversations.append({
            'user': other_user,
            'last_message': last_message,
            'unread_count': unread_count
        })
    
    conversations.sort(key=lambda x: x['last_message'].timestamp if x['last_message'] else datetime.min, reverse=True)
    
    return render_template('messages.html', conversations=conversations)

@app.route('/messages/<int:user_id>', methods=['GET', 'POST'])
def conversation(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    current_user_id = session['user_id']
    other_user = User.query.get_or_404(user_id)
    
    is_admin = session.get('is_admin', False)
    if not is_admin:
        accepted_request = ServiceRequest.query.join(Service).filter(
            ((ServiceRequest.seeker_id == current_user_id) & (Service.provider_id == user_id)) |
            ((ServiceRequest.seeker_id == user_id) & (Service.provider_id == current_user_id))
        ).filter(ServiceRequest.status.in_(['accepted', 'completed'])).first()
        
        if not accepted_request:
            flash('You must have an accepted service request before you can message this user.', 'warning')
            return redirect(request.referrer or url_for('dashboard'))
    
    if request.method == 'POST':
        content = request.form['content']
        
        if content.strip():
            new_message = Message(
                sender_id=current_user_id,
                receiver_id=user_id,
                content=content.strip()
            )
            db.session.add(new_message)
            db.session.commit()
            
            # Emit socket event to the receiver
            socketio.emit('new_message', {
                'id': new_message.id,
                'content': new_message.content,
                'sender_id': current_user_id,
                'timestamp': new_message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            }, room=f"user_{user_id}")
            socketio.emit('notification_ping', {}, room=f"user_{user_id}")
            
            return redirect(url_for('conversation', user_id=user_id))
    
    Message.query.filter_by(sender_id=user_id, receiver_id=current_user_id, is_read=False).update({'is_read': True})
    db.session.commit()
    
    messages = Message.query.filter(
        ((Message.sender_id == current_user_id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user_id))
    ).order_by(Message.timestamp.asc()).all()
    
    return render_template('conversation.html', messages=messages, other_user=other_user)

from flask import jsonify
@app.route('/api/messages/<int:user_id>', methods=['POST'])
def send_message_api(user_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    current_user_id = session['user_id']
    content = request.json.get('content')
    
    if not content or not content.strip():
        return jsonify({'error': 'Empty message'}), 400
        
    new_message = Message(
        sender_id=current_user_id,
        receiver_id=user_id,
        content=content.strip()
    )
    db.session.add(new_message)
    db.session.commit()
    
    # Emit events
    socketio.emit('new_message', {
        'id': new_message.id,
        'sender_id': current_user_id,
        'content': new_message.content,
        'timestamp': new_message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }, room=f"user_{user_id}")
    
    socketio.emit('notification_ping', {}, room=f"user_{user_id}")
    
    return jsonify({
        'success': True,
        'message': {
            'id': new_message.id,
            'content': new_message.content,
            'sender_id': current_user_id,
            'timestamp': new_message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }
    })

# Review Routes
@app.route('/add_review/<int:provider_id>', methods=['POST'])
def add_review(provider_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    reviewer_id = session['user_id']
    rating = request.form['rating']
    comment = request.form['comment']
    service_id = request.form.get('service_id')
    
    existing_review = Review.query.filter_by(
        reviewer_id=reviewer_id,
        reviewee_id=provider_id,
        service_id=service_id
    ).first()
    
    if existing_review:
        flash('You have already reviewed this provider for this service.', 'warning')
        return redirect(request.referrer or url_for('profile', user_id=provider_id))
    
    new_review = Review(
        reviewer_id=reviewer_id,
        reviewee_id=provider_id,
        service_id=service_id,
        rating=int(rating),
        comment=comment.strip() if comment else None
    )
    
    db.session.add(new_review)
    db.session.commit()
    
    flash('Review submitted successfully!', 'success')
    return redirect(request.referrer or url_for('profile', user_id=provider_id))

@app.route('/service_requests')
def service_requests():
    if 'user_id' not in session:
        flash('Please log in to view requests.', 'danger')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    # Sent Requests (Requests they made to others)
    sent_requests = ServiceRequest.query.filter_by(seeker_id=user_id).order_by(ServiceRequest.request_date.desc()).all()
    
    # Received Requests (Requests made to their services)
    services = Service.query.filter_by(provider_id=user_id).all()
    service_ids = [service.id for service in services]
    received_requests = ServiceRequest.query.filter(ServiceRequest.service_id.in_(service_ids)).order_by(ServiceRequest.request_date.desc()).all()
    
    return render_template('service_requests.html', sent_requests=sent_requests, received_requests=received_requests)

@app.route('/update_request_status/<int:request_id>', methods=['POST'])
def update_request_status(request_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    request_obj = ServiceRequest.query.get_or_404(request_id)
    service = Service.query.get(request_obj.service_id)
    user_id = session['user_id']
    new_status = request.form['status']
    
    if service.provider_id == user_id:
        pass
    elif request_obj.seeker_id == user_id and new_status == 'cancelled':
        pass
    else:
        flash('You are not authorized to update this request.', 'danger')
        return redirect(url_for('dashboard'))
    
    request_obj.status = new_status
    db.session.commit()
    
    flash(f'Request status updated to {new_status}.', 'success')
    return redirect(url_for('service_requests'))

# Admin Routes
from flask import jsonify

@app.route('/api/notifications')
def notifications():
    if 'user_id' not in session:
        return jsonify({'unread_messages': 0, 'pending_requests': 0})
        
    user_id = session['user_id']
    user_type = session.get('user_type')
    
    unread_messages = Message.query.filter_by(receiver_id=user_id, is_read=False).count()
    
    pending_requests = 0
    if user_type == 'provider':
        services = Service.query.filter_by(provider_id=user_id).all()
        service_ids = [s.id for s in services]
        if service_ids:
            pending_requests = ServiceRequest.query.filter(ServiceRequest.service_id.in_(service_ids), ServiceRequest.status == 'pending').count()
            
    return jsonify({
        'unread_messages': unread_messages,
        'pending_requests': pending_requests
    })

# Profile Management Routes
@app.route('/profile/edit', methods=['POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user = User.query.get(session['user_id'])
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')
    
    if name:
        user.name = name
    if email:
        if email != user.email:
            existing = User.query.filter_by(email=email).first()
            if existing:
                flash('Email already in use.', 'danger')
                return redirect(url_for('profile', user_id=user.id))
            user.email = email
    if password:
        user.password = generate_password_hash(password)
        
    db.session.commit()
    session['user_name'] = user.name
    flash('Profile updated successfully!', 'success')
    return redirect(url_for('profile', user_id=user.id))

@app.route('/profile/delete', methods=['POST'])
def delete_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user = User.query.get(session['user_id'])
    
    if user.profile_picture:
        picture_path = os.path.join(app.config['UPLOAD_FOLDER'], user.profile_picture)
        if os.path.exists(picture_path):
            os.remove(picture_path)
            
    if user.student_id_document:
        doc_path = os.path.join(app.config['UPLOAD_FOLDER_DOCS'], user.student_id_document)
        if os.path.exists(doc_path):
            os.remove(doc_path)
            
    ServiceRequest.query.filter((ServiceRequest.seeker_id == user.id)).delete()
    services = Service.query.filter_by(provider_id=user.id).all()
    for s in services:
        ServiceRequest.query.filter_by(service_id=s.id).delete()
        Review.query.filter_by(service_id=s.id).delete()
    Service.query.filter_by(provider_id=user.id).delete()
    Message.query.filter((Message.sender_id == user.id) | (Message.receiver_id == user.id)).delete()
    Review.query.filter((Review.reviewer_id == user.id) | (Review.reviewee_id == user.id)).delete()
    
    db.session.delete(user)
    db.session.commit()
    
    session.clear()
    flash('Your account has been permanently deleted.', 'success')
    return redirect(url_for('index'))

# Service Management Routes
@app.route('/service/<int:service_id>/edit', methods=['GET', 'POST'])
def edit_service(service_id):
    if 'user_id' not in session or session.get('user_type') != 'provider':
        return redirect(url_for('login'))
        
    service = Service.query.get_or_404(service_id)
    if service.provider_id != session['user_id'] and not session.get('is_admin'):
        flash('Unauthorized.', 'danger')
        return redirect(url_for('dashboard'))
        
    categories = [cat[0] for cat in db.session.query(Service.category).distinct().all()]
    if service.category not in categories:
        categories.append(service.category)
    
    if request.method == 'POST':
        service.title = request.form['title']
        service.description = request.form['description']
        service.category = request.form['category']
        service.price = request.form['price']
        service.location = request.form['location']
        service.contact_info = request.form['contact_info']
        service.is_active = request.form.get('is_active') == 'on'
        
        db.session.commit()
        flash('Service updated successfully!', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('edit_service.html', service=service, categories=categories)

@app.route('/service/<int:service_id>/delete', methods=['POST'])
def delete_service(service_id):
    if 'user_id' not in session or session.get('user_type') != 'provider':
        return redirect(url_for('login'))
        
    service = Service.query.get_or_404(service_id)
    if service.provider_id != session['user_id'] and not session.get('is_admin'):
        flash('Unauthorized.', 'danger')
        return redirect(url_for('dashboard'))
        
    ServiceRequest.query.filter_by(service_id=service.id).delete()
    Review.query.filter_by(service_id=service.id).delete()
    db.session.delete(service)
    db.session.commit()
    
    flash('Service deleted successfully.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_services = Service.query.count()
    total_requests = ServiceRequest.query.count()
    pending_verifications = User.query.filter_by(verification_status='pending').count()
    return render_template('admin_dashboard.html', 
                           total_users=total_users, 
                           total_services=total_services, 
                           total_requests=total_requests,
                           pending_verifications=pending_verifications)

@app.route('/api/admin/analytics')
@admin_required
def admin_analytics():
    seekers = User.query.filter_by(user_type='seeker').count()
    providers = User.query.filter_by(user_type='provider').count()
    
    categories_data = db.session.query(Service.category, db.func.count(Service.id)).group_by(Service.category).all()
    categories = {cat: count for cat, count in categories_data}
    
    status_data = db.session.query(ServiceRequest.status, db.func.count(ServiceRequest.id)).group_by(ServiceRequest.status).all()
    requests_status = {status: count for status, count in status_data}
    
    ratings = db.session.query(db.func.avg(Review.rating)).scalar() or 0.0
    avg_rating = round(float(ratings), 2)
    
    return jsonify({
        'user_distribution': {
            'seekers': seekers,
            'providers': providers
        },
        'categories': categories,
        'requests_status': requests_status,
        'average_rating': avg_rating
    })

@app.route('/admin/export/users')
@admin_required
def export_users_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['User ID', 'Name', 'Email', 'Role', 'Verification Status', 'Is Admin', 'Registration Date'])
    
    users = User.query.all()
    for u in users:
        writer.writerow([
            u.id, 
            u.name, 
            u.email, 
            u.user_type, 
            u.verification_status, 
            'Yes' if u.is_admin else 'No', 
            u.registration_date.strftime('%Y-%m-%d %H:%M:%S') if u.registration_date else ''
        ])
        
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=uniserve_users_report.csv"}
    )

@app.route('/admin/export/services')
@admin_required
def export_services_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Service ID', 'Title', 'Category', 'Price', 'Location', 'Provider Name', 'Provider Email', 'Is Active', 'Created Date'])
    
    services = Service.query.all()
    for s in services:
        provider = User.query.get(s.provider_id)
        provider_name = provider.name if provider else 'N/A'
        provider_email = provider.email if provider else 'N/A'
        
        writer.writerow([
            s.id,
            s.title,
            s.category,
            s.price or 'N/A',
            s.location,
            provider_name,
            provider_email,
            'Active' if s.is_active else 'Inactive',
            s.created_date.strftime('%Y-%m-%d %H:%M:%S') if s.created_date else ''
        ])
        
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=uniserve_services_report.csv"}
    )

@app.route('/admin/export/requests')
@admin_required
def export_requests_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Request ID', 'Service Title', 'Provider Name', 'Seeker Name', 'Seeker Email', 'Status', 'Request Date'])
    
    requests = ServiceRequest.query.all()
    for r in requests:
        service = Service.query.get(r.service_id)
        service_title = service.title if service else 'N/A'
        
        provider = User.query.get(service.provider_id) if service else None
        provider_name = provider.name if provider else 'N/A'
        
        seeker = User.query.get(r.seeker_id)
        seeker_name = seeker.name if seeker else 'N/A'
        seeker_email = seeker.email if seeker else 'N/A'
        
        writer.writerow([
            r.id,
            service_title,
            provider_name,
            seeker_name,
            seeker_email,
            r.status.capitalize(),
            r.request_date.strftime('%Y-%m-%d %H:%M:%S') if r.request_date else ''
        ])
        
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=uniserve_requests_report.csv"}
    )

@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/verifications')
@admin_required
def admin_verifications():
    pending_users = User.query.filter_by(verification_status='pending').all()
    verified_users = User.query.filter_by(verification_status='verified').all()
    rejected_users = User.query.filter_by(verification_status='rejected').all()
    return render_template('admin_verifications.html', pending_users=pending_users, verified_users=verified_users, rejected_users=rejected_users)

@app.route('/admin/verify/<int:user_id>', methods=['POST'])
@admin_required
def update_verification_status(user_id):
    user = User.query.get_or_404(user_id)
    new_status = request.form.get('status')
    
    if new_status in ['verified', 'rejected', 'unverified']:
        user.verification_status = new_status
        db.session.commit()
        flash(f'User {user.name} verification status updated to {new_status}.', 'success')
        
    return redirect(url_for('admin_verifications'))

@app.route('/admin/user/<int:user_id>/promote', methods=['POST'])
@admin_required
def promote_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == session['user_id']:
        flash('You cannot promote yourself.', 'warning')
    elif user.is_admin:
        flash(f'User {user.name} is already an admin.', 'info')
    else:
        user.is_admin = True
        db.session.commit()
        flash(f'User {user.name} promoted to admin.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == session['user_id']:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin_users'))
    
    if user.profile_picture:
        picture_path = os.path.join(app.config['UPLOAD_FOLDER'], user.profile_picture)
        if os.path.exists(picture_path):
            pass # Or try to remove
            
    if user.student_id_document:
        doc_path = os.path.join(app.config['UPLOAD_FOLDER_DOCS'], user.student_id_document)
        if os.path.exists(doc_path):
            os.remove(doc_path)
    
    ServiceRequest.query.filter((ServiceRequest.seeker_id == user.id)).delete()
    services = Service.query.filter_by(provider_id=user.id).all()
    for s in services:
        ServiceRequest.query.filter_by(service_id=s.id).delete()
        Review.query.filter_by(service_id=s.id).delete()
    Service.query.filter_by(provider_id=user.id).delete()
    Message.query.filter((Message.sender_id == user.id) | (Message.receiver_id == user.id)).delete()
    Review.query.filter((Review.reviewer_id == user.id) | (Review.reviewee_id == user.id)).delete()
    
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.name} deleted successfully.', 'success')
    return redirect(url_for('admin_users'))

# Initialize database
def init_db():
    with app.app_context():
        db.create_all()
        # Migrations are now handled on app import (lines 115-139)
        print("[SUCCESS] Database initialized successfully!")
        print("[SUCCESS] All tables created and migrations applied")

if __name__ == '__main__':
    init_db()
    # allow_unsafe_werkzeug=True is required when using the threading async mode locally
    socketio.run(app, debug=DEBUG, allow_unsafe_werkzeug=True)