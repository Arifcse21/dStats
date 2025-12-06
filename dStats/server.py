# dStats/server.py
import os
import sys
import signal
import subprocess
from daphne.cli import CommandLineInterface

DB_FILE = "dStats.sqlite3"


def remove_dStats_db_file():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    else:
        pass


def signal_handler(signum, frame):
    """Signal handler for graceful shutdown."""
    print("\nReceived interrupt signal.")
    remove_dStats_db_file()
    print("dStats server stopped by user.")
    print("Bye bye!")
    sys.exit(0)


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dStats.settings")

    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal

    command = ["daphne", "-b", "0.0.0.0", "-p", "2743", "dStats.asgi:application"]

    try:
        subprocess.run(command)
    except KeyboardInterrupt:
        print("\nCaught KeyboardInterrupt in main process.")
        signal_handler(signal.SIGINT, None)
    except subprocess.CalledProcessError as e:
        # This catches errors where daphne returned a non-zero exit code
        print(f"Daphne exited with error code: {e.returncode}")
    except Exception as e:
        print(f"An unexpected error occurred while running Daphne: {e}")


if __name__ == "__main__":
    main()
