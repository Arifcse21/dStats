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

        existing = User.objects.filter(username=auth_username).first()
        if existing is not None:
            # Keep the stored password in step with AUTH_PASSWORD, so changing it
            # actually revokes the old one
            if not existing.check_password(auth_password):
                existing.set_password(auth_password)
                existing.save(update_fields=["password"])
                print(f"Password for {auth_username} updated from AUTH_PASSWORD")
        else:
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

        # Only the configured account may log in; renaming AUTH_USERNAME locks out the old one
        User.objects.exclude(username=auth_username).update(is_active=False)
        User.objects.filter(username=auth_username).update(is_active=True)

    except Exception as e:
        print(f"\033[91mError during auto-migration or superuser creation: {e}\033[0m")
