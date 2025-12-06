from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Create a superuser with password"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username", type=str, help="Username for the new superuser"
        )
        parser.add_argument(
            "--password", type=str, help="Password for the new superuser"
        )

    def handle(self, *args, **options):
        username = options.get("username") or input("Enter username: ")
        password = options.get("password") or input("Enter password: ")

        # Create the superuser
        user = User.objects.create_superuser(username=username, password=password)

        self.stdout.write(
            self.style.SUCCESS(f"Successfully created superuser: {username}")
        )
