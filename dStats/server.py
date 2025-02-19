import os
import sys
import subprocess
from daphne.cli import CommandLineInterface


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dStats.settings")

    # Construct the command to run Daphne
    command = ["daphne", "-b", "0.0.0.0", "-p", "2743", "dStats.asgi:application"]
    try:
        # Run the command
        subprocess.run(command)
    except KeyboardInterrupt:
        print("\ndStats server stopped by user.")
        print("Bye bye!")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
