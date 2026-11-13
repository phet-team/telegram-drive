from django.apps import AppConfig


class DriveConfig(AppConfig):
    name = 'drive'

    def ready(self):
        from drive import signals  # noqa: F401  (connects the model signals)
