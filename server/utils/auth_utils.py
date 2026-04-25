"""JWT token utilities for authentication"""
import jwt
import logging
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from server.models import User, RefreshToken
from server.middleware.database import db

logger = logging.getLogger('calliope-ide')

JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
if not JWT_SECRET_KEY:
    raise EnvironmentError(
        "JWT_SECRET_KEY environment variable is not set. "
        "Generate a secure key with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))
JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 2592000))
JWT_ALGORITHM = 'HS256'


def generate_access_token(user_id, username):
    """Generate JWT access token"""
    payload = {
        'user_id': user_id,
        'username': username,
        'type': 'access',
        'exp': datetime.utcnow() + timedelta(seconds=JWT_ACCESS_TOKEN_EXPIRES),
        'iat': datetime.utcnow()
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    logger.info(
        'access_token_generated',
        extra={
            'event': 'access_token_generated',
            'user_id': user_id,
            'username': username,
        },
    )
    return token


def generate_refresh_token(user_id, username):
    """Generate JWT refresh token and store in database"""
    payload = {
        'user_id': user_id,
        'username': username,
        'type': 'refresh',
        'exp': datetime.utcnow() + timedelta(seconds=JWT_REFRESH_TOKEN_EXPIRES),
        'iat': datetime.utcnow()
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    refresh_token = RefreshToken(
        user_id=user_id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(seconds=JWT_REFRESH_TOKEN_EXPIRES)
    )
    db.session.add(refresh_token)
    db.session.commit()

    logger.info(
        'refresh_token_generated',
        extra={
            'event': 'refresh_token_generated',
            'user_id': user_id,
            'username': username,
        },
    )
    return token


def decode_token(token):
    """Decode and verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning(
            'token_expired',
            extra={'event': 'token_expired'},
        )
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning(
            'token_invalid',
            extra={'event': 'token_invalid', 'reason': str(exc)},
        )
        return None


def token_required(f):
    """Decorator to protect routes requiring authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(' ')[1]
            except IndexError:
                logger.warning(
                    'auth_header_malformed',
                    extra={
                        'event': 'auth_header_malformed',
                        'path': request.path,
                    },
                )
                return jsonify({
                    'success': False,
                    'error': 'Invalid authorization header format. Use: Bearer <token>'
                }), 401

        if not token:
            logger.warning(
                'auth_token_missing',
                extra={
                    'event': 'auth_token_missing',
                    'path': request.path,
                    'method': request.method,
                },
            )
            return jsonify({
                'success': False,
                'error': 'Authentication token is missing'
            }), 401

        payload = decode_token(token)

        if not payload:
            return jsonify({
                'success': False,
                'error': 'Invalid or expired token'
            }), 401

        if payload.get('type') != 'access':
            logger.warning(
                'auth_wrong_token_type',
                extra={
                    'event': 'auth_wrong_token_type',
                    'token_type': payload.get('type'),
                    'path': request.path,
                },
            )
            return jsonify({
                'success': False,
                'error': 'Invalid token type'
            }), 401

        current_user = User.query.filter_by(id=payload['user_id']).first()

        if not current_user:
            logger.warning(
                'auth_user_not_found',
                extra={
                    'event': 'auth_user_not_found',
                    'user_id': payload.get('user_id'),
                    'path': request.path,
                },
            )
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 401

        if not current_user.is_active:
            logger.warning(
                'auth_user_deactivated',
                extra={
                    'event': 'auth_user_deactivated',
                    'user_id': current_user.id,
                    'username': current_user.username,
                    'path': request.path,
                },
            )
            return jsonify({
                'success': False,
                'error': 'Account is deactivated'
            }), 403

        logger.info(
            'auth_success',
            extra={
                'event': 'auth_success',
                'user_id': current_user.id,
                'username': current_user.username,
                'path': request.path,
                'method': request.method,
            },
        )

        return f(current_user, *args, **kwargs)

    return decorated


def revoke_refresh_token(token):
    """Revoke a refresh token"""
    refresh_token = RefreshToken.query.filter_by(token=token).first()
    if refresh_token:
        refresh_token.is_revoked = True
        db.session.commit()
        logger.info(
            'refresh_token_revoked',
            extra={
                'event': 'refresh_token_revoked',
                'user_id': refresh_token.user_id,
            },
        )
        return True
    logger.warning(
        'refresh_token_revoke_not_found',
        extra={'event': 'refresh_token_revoke_not_found'},
    )
    return False