# dStats/server.py
import argparse
import os
import sys
import signal
import subprocess
from daphne.cli import CommandLineInterface
from decouple import config

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
    parser = argparse.ArgumentParser(
        prog="dStats.server",
        description="Real-time stats and network graph for Docker and Podman containers.",
    )
    parser.add_argument(
        "--engine",
        help="container engine(s) to monitor: docker (default), podman, or docker,podman "
        "for both; same as the DSTATS_ENGINE environment variable",
    )
    args = parser.parse_args()

    from dStats.engines import configured_engines, parse_engines

    if args.engine:
        try:
            parse_engines(args.engine)
        except ValueError as e:
            parser.error(str(e))
        # Environment, so the daphne process started below sees it too
        os.environ["DSTATS_ENGINE"] = args.engine

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dStats.settings")

    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal

    from dStats.settings import is_auth_enabled, is_loopback, listen_host

    host = listen_host()
    port = config("DSTATS_PORT", default="2743")

    try:
        engines = configured_engines()
    except ValueError as e:
        parser.error(f"DSTATS_ENGINE: {e}")
    for engine in engines:
        path = engine.url.removeprefix("unix://")
        missing = engine.url.startswith("unix://") and not os.path.exists(path)
        print(
            f"Monitoring {engine.name} at {engine.url}"
            + (" (not found yet)" if missing else "")
        )
        if missing and engine.name == "podman":
            print(
                "  Start Podman's API with: systemctl --user enable --now podman.socket"
            )

    if not is_auth_enabled():
        if is_loopback(host):
            print(
                f"dStats is only reachable from this machine (http://localhost:{port}).\n"
                "To open it to your network, set AUTH_USERNAME and AUTH_PASSWORD with "
                "USE_AUTH=true,\nor set DSTATS_HOST=0.0.0.0 to expose it without a login."
            )
        else:
            print(
                f"\033[91mWARNING: authentication is off and dStats listens on {host}:{port}; "
                "anyone who can reach it can see your containers.\033[0m"
            )

    # Same interpreter as dStats, so it works without an activated virtualenv
    command = [
        sys.executable,
        "-m",
        "daphne",
        "-b",
        host,
        "-p",
        port,
        "dStats.asgi:application",
    ]

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
