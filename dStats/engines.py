"""Which container engines dStats monitors and where their API sockets live.

Podman serves the same API as Docker (enable it with
`systemctl --user enable --now podman.socket`), so both engines are queried the
same way; only the socket path differs.
"""

import os
from dataclasses import dataclass

from decouple import config

SUPPORTED_ENGINES = ("docker", "podman")

ENGINE_LABELS = {"docker": "Docker", "podman": "Podman"}

START_HINTS = {
    "docker": "Is the Docker daemon running, and can this user access its socket?",
    "podman": "Start its API with: systemctl --user enable --now podman.socket",
}


class EngineUnavailable(Exception):
    """An engine's API couldn't be reached; the message is shown on the dashboard."""


@dataclass(frozen=True)
class Engine:
    name: str
    url: str


def parse_engines(value):
    """Turn "docker", "podman" or "docker,podman" into a list of engine names."""
    names = []
    for name in value.split(","):
        name = name.strip().lower()
        if not name:
            continue
        if name not in SUPPORTED_ENGINES:
            raise ValueError(
                f"Unknown container engine {name!r}; "
                f"use {', '.join(SUPPORTED_ENGINES)} or a comma-separated list of them"
            )
        if name not in names:
            names.append(name)
    if not names:
        raise ValueError("No container engine selected")
    return names


def engine_names():
    return parse_engines(config("DSTATS_ENGINE", default="docker"))


def socket_url(name):
    if name == "docker":
        return config("DOCKER_HOST", default="unix:///var/run/docker.sock")

    # CONTAINER_HOST is Podman's own equivalent of DOCKER_HOST
    if host := config("CONTAINER_HOST", default=""):
        return host
    candidates = []
    if runtime_dir := os.environ.get("XDG_RUNTIME_DIR"):
        candidates.append(f"{runtime_dir}/podman/podman.sock")  # rootless
    candidates.append("/run/podman/podman.sock")  # rootful, or mounted into a container
    for path in candidates:
        # Skip sockets this user can't open, e.g. root's when running rootless
        if os.access(path, os.R_OK | os.W_OK):
            return f"unix://{path}"
    # Nothing running yet; report the most likely path in errors
    return f"unix://{candidates[0]}"


def configured_engines():
    # Resolved on every call, so a socket started after dStats is still picked up
    return [Engine(name, socket_url(name)) for name in engine_names()]
