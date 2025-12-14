from django.apps import AppConfig


class MemosConfig(AppConfig):
    name = 'memos'
    
    def ready(self):
        import memos.signals  # noqa
