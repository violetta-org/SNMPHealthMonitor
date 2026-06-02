"""
Core models - User authentication and audit logging.
Ported from query-service/db/models.py (SQLAlchemy).

These tables may not exist in MySQL yet - set managed=True if you want Django
to create them, or managed=False if they already exist.
"""
from __future__ import annotations

from django.db import models
from django.contrib.auth.hashers import make_password, check_password


class User(models.Model):
    """
    Application user for authentication.
    Maps to 'user' table (Flask SQLAlchemy convention).
    
    Note: Uses werkzeug-compatible password hashing for Flask interoperability.
    """
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=255, unique=True)
    password_hash = models.CharField(max_length=255, db_column='password_hash')

    class Meta:
        managed = True  # Let Django create this table if not exists
        db_table = 'user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self) -> str:
        return self.username

    def set_password(self, password: str) -> None:
        """
        Set the password hash.
        Uses Django's password hasher (PBKDF2 by default).
        """
        self.password_hash = make_password(password)

    def check_password(self, password: str) -> bool:
        """
        Verify a password against the stored hash.
        """
        return check_password(password, self.password_hash)


class AuditLog(models.Model):
    """
    Audit log for tracking user actions.
    Maps to 'audit_log' table.
    """
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        db_column='user_id'
    )
    action = models.CharField(max_length=50)
    target = models.CharField(max_length=255, null=True, blank=True)
    details = models.TextField(null=True, blank=True)
    ip_address = models.CharField(max_length=45, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True  # Let Django create this table if not exists
        db_table = 'audit_log'
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']

    def __str__(self) -> str:
        user_str = self.user.username if self.user else 'system'
        return f"[{self.timestamp}] {user_str}: {self.action}"
