from django.core.management import call_command
from django.db import connection
from decouple import config


def migrate_and_create_user():
    try:
        # Check if migration tables exist
        tables = connection.introspection.table_names()

        # If django_migrations table doesn't exist, we need to run initial setup
        if "django_migrations" not in tables:
            print("Database not initialized, running initial migrations...")
            call_command("migrate", verbosity=1)
            print("Migrations completed!")
        else:
            # Check if auth tables exist
            if "auth_user" not in tables:
                print("Auth tables missing, running migrations...")
                call_command("migrate", verbosity=1)
                print("Migrations completed!")

        # Now create the user if it doesn't exist
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Get username and password from environment variables
        auth_username = config("AUTH_USERNAME")
        auth_password = config("AUTH_PASSWORD")

        if not User.objects.filter(username=auth_username).exists():
            print(f"Creating user {auth_username}...")
            # Call your management command to create the user
            call_command(
                "create_user",  # Replace with your actual command name
                "--username",
                auth_username,
                "--password",
                auth_password,
                verbosity=2,  # Set to 1 or 2 for more output
            )
            print(f"User {auth_username} created!")

    except Exception as e:
        print(f"\033[91mError during auto-migration or superuser creation: {e}\033[0m")
