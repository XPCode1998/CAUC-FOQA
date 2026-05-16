from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.api"

    def ready(self):
        from .backup_scheduler import start_backup_scheduler

        start_backup_scheduler()
