from django.apps import AppConfig
from django.conf import settings
import os


class FilesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.files'
    verbose_name = 'File Management'

    def ready(self):
        """Ensure required directories exist on startup."""
        for d in [settings.HOME_DIRECTORY, settings.TRASH_DIRECTORY, settings.BACKUP_DIRECTORY]:
            os.makedirs(d, exist_ok=True)
