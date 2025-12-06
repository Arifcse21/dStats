import os
from django.apps import AppConfig


class AuthbootConfig(AppConfig):
    name = "authboot"

    def ready(self):
        from authboot.utils import migrate_and_create_user

        migrate_and_create_user()
