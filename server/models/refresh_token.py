

from datetime import datetime
from server.middleware.database import db

class RefreshToken(db.Model):
    """Model for storing refresh tokens"""
    
    __tablename__ = 'refresh_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(500), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_revoked = db.Column(db.Boolean, default=False)
    user = db.relationship('User', backref=db.backref('refresh_tokens', lazy=True))
    
    def __repr__(self):
        return f'<RefreshToken {self.id} for User {self.user_id}>'