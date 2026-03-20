import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import re
from datetime import datetime

app = Flask(__name__)

# Configuration - Different for development vs production
if os.environ.get('RENDER'):  # Render.com
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace('postgres://', 'postgresql://')
    DEBUG = False
else:  # Local development
    app.config['SECRET_KEY'] = 'uniserve-secret-key-2024'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
    DEBUG = True

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
app.config['UPLOAD_FOLDER'] = 'static/uploads/profile_pictures'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

db = SQLAlchemy(app)

# Database Models (Keep all your existing models exactly as they are)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)
    profile_picture = db.Column(db.String(200), nullable=True)
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

# Ensure tables are created automatically on import (solves database initialization on Render)
with app.app_context():
    db.create_all()

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
        
        # Validate university email
        if not re.match(r'.*@(uict\.ac\.ug|student\.uict\.ac\.ug)$', email):
            flash('Please use a valid UICT email address.', 'danger')
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
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_type'] = user.user_type
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
    if 'user_id' not in session or session['user_type'] != 'seeker':
        flash('Please login as a service seeker to request services.', 'danger')
        return redirect(url_for('login'))
    
    service_id = request.form['service_id']
    message = request.form['message']
    
    new_request = ServiceRequest(
        service_id=service_id,
        seeker_id=session['user_id'],
        message=message
    )
    
    db.session.add(new_request)
    db.session.commit()
    
    flash('Service request sent successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/profile/<int:user_id>')
def profile(user_id):
    user = User.query.get_or_404(user_id)
    reviews = Review.query.filter_by(reviewee_id=user_id).all()
    
    avg_rating = 0
    if reviews:
        avg_rating = sum([review.rating for review in reviews]) / len(reviews)
    
    return render_template('profile.html', user=user, reviews=reviews, avg_rating=avg_rating)

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
        unique_filename = f"user_{user.id}_{filename}"
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
            
            return redirect(url_for('conversation', user_id=user_id))
    
    Message.query.filter_by(sender_id=user_id, receiver_id=current_user_id, is_read=False).update({'is_read': True})
    db.session.commit()
    
    messages = Message.query.filter(
        ((Message.sender_id == current_user_id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user_id))
    ).order_by(Message.timestamp.asc()).all()
    
    return render_template('conversation.html', messages=messages, other_user=other_user)

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
    if 'user_id' not in session or session['user_type'] != 'provider':
        flash('Only service providers can access this page.', 'danger')
        return redirect(url_for('dashboard'))
    
    provider_id = session['user_id']
    
    services = Service.query.filter_by(provider_id=provider_id).all()
    service_ids = [service.id for service in services]
    
    requests = ServiceRequest.query.filter(ServiceRequest.service_id.in_(service_ids)).order_by(ServiceRequest.request_date.desc()).all()
    
    return render_template('service_requests.html', requests=requests)

@app.route('/update_request_status/<int:request_id>', methods=['POST'])
def update_request_status(request_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    request_obj = ServiceRequest.query.get_or_404(request_id)
    service = Service.query.get(request_obj.service_id)
    
    if service.provider_id != session['user_id']:
        flash('You are not authorized to update this request.', 'danger')
        return redirect(url_for('dashboard'))
    
    new_status = request.form['status']
    request_obj.status = new_status
    db.session.commit()
    
    flash(f'Request status updated to {new_status}.', 'success')
    return redirect(url_for('service_requests'))

# Initialize database
def init_db():
    with app.app_context():
        db.create_all()
        print("[SUCCESS] Database initialized successfully!")
        print("[SUCCESS] All tables created with profile_picture column")

if __name__ == '__main__':
    init_db()
    app.run(debug=DEBUG)