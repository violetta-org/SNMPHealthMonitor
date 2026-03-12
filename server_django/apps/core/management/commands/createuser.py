"""
Management command to create a user for the SNMPHealthMonitor app.

Usage:
    python manage.py createuser admin mypassword
    python manage.py createuser --username admin --password mypassword
"""
from django.core.management.base import BaseCommand
from apps.core.models import User


class Command(BaseCommand):
    help = 'Create a user for the SNMPHealthMonitor app'

    def add_arguments(self, parser):
        parser.add_argument('username', nargs='?', type=str, help='Username')
        parser.add_argument('password', nargs='?', type=str, help='Password')
        parser.add_argument('--username', dest='opt_username', type=str, help='Username (optional flag)')
        parser.add_argument('--password', dest='opt_password', type=str, help='Password (optional flag)')

    def handle(self, *args, **options):
        username = options.get('username') or options.get('opt_username')
        password = options.get('password') or options.get('opt_password')

        if not username:
            username = input('Username: ').strip()
        if not password:
            import getpass
            password = getpass.getpass('Password: ')

        if not username or not password:
            self.stderr.write(self.style.ERROR('Username and password are required.'))
            return

        user, created = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f'User "{username}" created successfully.'))
        else:
            self.stdout.write(self.style.WARNING(f'User "{username}" already exists — password updated.'))
