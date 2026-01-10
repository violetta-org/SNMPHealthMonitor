"""
WSGI config for SNMPHealthMonitor Django project.
Only used for traditional sync deployments (not recommended).
For WebSocket support, use asgi.py with Daphne.
"""
import os

# PyMySQL monkey-patch
import pymysql
pymysql.install_as_MySQLdb()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
