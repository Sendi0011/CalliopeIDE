"""
Middleware for Calliope IDE
"""

from .database import db, init_db

__all__ = ['db', 'init_db']