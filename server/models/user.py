"""User models for authentication"""
import bcrypt
from datetime import datetime
from server.middleware.database import db


class User(db.Model):
    """User model for storing user account information"""
    
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150))
    avatar_url = db.Column(db.String(500))
    bio = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    def __init__(self, email, username, password, full_name=None):
        self.email = email.lower().strip()
        self.username = username.strip()
        self.full_name = full_name
        self.set_password(password)
    
    def set_password(self, password):
        """Hash and set the user's password"""
        salt = bcrypt.gensalt()
        password_bytes = password.encode('utf-8')
        self.password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
    
    def check_password(self, password):
        """Verify password against stored hash"""
        password_bytes = password.encode('utf-8')
        hash_bytes = self.password_hash.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hash_bytes)
    
    def update_last_login(self):
        """Update the last login timestamp"""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def to_dict(self, include_sensitive=False):
        """Convert user object to dictionary"""
        data = {
            'id': self.id,
            'email': self.email,
            'username': self.username,
            'full_name': self.full_name,
            'avatar_url': self.avatar_url,
            'bio': self.bio,
            'is_verified': self.is_verified,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
        if include_sensitive:
            data.update({
                'is_active': self.is_active,
                'is_admin': self.is_admin,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None
            })
        return data
    
    def __repr__(self):
        return f'<User {self.username}>'

