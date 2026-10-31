# Developing dStats

How to run dStats from a checkout, build the Python package and container image,
publish a release, and work with Docker, Podman, or both.

For using dStats (not developing it), see [README.md](README.md).

---

## 1. Prerequisites

| Tool | Needed for | Install |
|---|---|---|
| Python 3.12+ | everything | your OS package manager |
| Graphviz (`dot`) | only the PNG graph from the JSON API (`GET /?type=graph`); the dashboard draws its graph in the browser | `apt install graphviz` · `dnf install graphviz` · `pacman -S graphviz` · `brew install graphviz` |
| Docker and/or Podman | something to monitor | [Docker](https://docs.docker.com/engine/install/) · [Podman](https://podman.io/docs/installation) |
| Rust (optional) | the native accelerator | `curl -sSf https://sh.rustup.rs \| sh` |

Without Rust, everything still works: dStats falls back to a threaded Python
implementation for collecting container stats.

---

## 2. Run locally

```bash
git clone https://github.com/Arifcse21/dStats.git
cd dStats
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"     # editable install + black, uv, twine
dStats.server               # http://localhost:2743
```

`pip install -e .` also compiles the Rust accelerator in place when Rust is installed.
Python changes take effect when you restart the server; after editing
`rust/src/lib.rs`, run `pip install -e .` again.

Check which implementation is active:

```bash
python -c "from dStats import _rust; print('Rust accelerator active')"
# ImportError means the Python fallback is in use
```

### Common options

```bash
dStats.server --engine podman                 # see section 3
DSTATS_PORT=8000 dStats.server                # another port
USE_AUTH=true AUTH_USERNAME=me AUTH_PASSWORD=secret dStats.server   # login; also opens it to the network
DSTATS_HOST=0.0.0.0 dStats.server             # open to the network WITHOUT a login (not recommended)
DEBUG=true dStats.server                      # Django debug pages; never on a reachable server
```

Without authentication, dStats listens on `127.0.0.1` only. Settings can also go in a
`.env` file in the directory you start it from; the full list is in the
[Configuration section of the README](README.md#configuration).

`dStats.server` stores its login database in `dStats.sqlite3` in the current directory
and deletes it on shutdown; the user is recreated from `AUTH_*` on the next start.

---

## 3. Container engines: Docker, Podman, or both

dStats reads everything through the Docker-compatible API. Docker provides it out of the
box; Podman provides it once its API socket is enabled.

| Command | Navbar | Queried |
|---|---|---|
| `dStats.server` | "Engine: Docker" | Docker |
| `dStats.server --engine podman` | "Engine: Podman" | Podman |
| `dStats.server --engine docker,podman` | Docker / Podman toggle | only the engine selected in each open browser |

`--engine` and the `DSTATS_ENGINE` environment variable are equivalent; a typo fails at startup.
With both enabled, the toggle choice is remembered per browser. If an engine can't be
reached, its panels say so with a hint, and the server logs the outage once.

### Docker

Your user needs access to the Docker socket:

```bash
sudo usermod -aG docker $USER    # then log out and back in
docker ps                        # must work without sudo
```

### Podman

Enable Podman's API socket once:

```bash
systemctl --user enable --now podman.socket      # rootless (your user's containers)
sudo systemctl enable --now podman.socket        # rootful (root's containers)
podman --remote ps                                # checks that the API answers
```

Rootless Podman only shows the current user's containers. That's expected: every user has
their own Podman.

### Where dStats looks for each engine

| Engine | Order |
|---|---|
| Docker | `DOCKER_HOST`, then `/var/run/docker.sock` |
| Podman | `CONTAINER_HOST`, then `$XDG_RUNTIME_DIR/podman/podman.sock` (rootless), then `/run/podman/podman.sock` (rootful) |

The startup output lists the socket used for each engine and says "(not found yet)" if
it's missing. Sockets are looked up again on every refresh, so starting an engine
after dStats is fine.

> Don't point `DOCKER_HOST` at Podman's socket while monitoring both engines, or the
> Docker tab will show your Podman containers.

### Trying both engines on one machine

`scripts/demo-containers.sh up` starts 10 tiny containers per engine on overlapping networks
(`down` removes them). Or by hand:

```bash
systemctl --user enable --now podman.socket
podman run -d --name demo-podman docker.io/library/nginx:alpine
docker run -d --name demo-docker nginx:alpine
dStats.server --engine docker,podman
# open http://localhost:2743 and switch engines in the navbar
podman rm -f demo-podman && docker rm -f demo-docker
```

---

## 4. Checks before committing

There is no automated test suite yet; these are the checks CI and releases rely on:

```bash
black dStats authboot                          # format Python
python manage.py check                         # Django configuration
cd rust && cargo fmt && cargo clippy --release --locked && cd ..   # format + lint Rust
```

Dependency audits (the release workflow runs both and blocks publishing on findings):

```bash
pip install pip-audit && pip-audit -r requirements.txt -s osv && pip-audit . -s osv
cargo install cargo-audit --locked && (cd rust && cargo audit)
```

---

## 5. Build the Python package

```bash
pip install build
python -m build                                  # sdist + native wheel for this machine (needs Rust)
DSTATS_PURE_PYTHON=1 python -m build --wheel     # pure-Python fallback wheel
ls dist/
```

Wheels install anywhere with `pip install dist/<file>.whl`.

**Don't upload these with twine.** A wheel built directly on Linux is tagged
`linux_x86_64`, which PyPI rejects, and it would only cover your platform. To build the
same portable `manylinux`/`musllinux` wheels CI produces, use cibuildwheel. It runs the
build inside a container, using either engine:

```bash
pip install "cibuildwheel>=3,<4"
cibuildwheel --platform linux --output-dir wheelhouse                                # with Docker
CIBW_CONTAINER_ENGINE=podman cibuildwheel --platform linux --output-dir wheelhouse   # with Podman
```

How the package is put together:

- `pyproject.toml` holds the metadata, dependencies and cibuildwheel settings.
- `setup.py` adds the Rust extension `dStats._rust` (from `rust/`) as **optional**:
  building from source without Rust still installs dStats.
- The extension uses the stable ABI (`abi3`), so one wheel per platform covers Python 3.12+.
- `rust/Cargo.lock` pins Rust dependencies; builds use `--locked`, so keep the lock file committed.

---

## 6. Publish a release

Releases are built and published by `.github/workflows/release.yml`, not from your machine.

### One-time setup

1. On PyPI, open the dStats project → **Settings → Publishing** and add a GitHub
   trusted publisher: owner `Arifcse21`, repository `dStats`, workflow `release.yml`,
   environment `pypi`.
2. On GitHub, create an environment named `pypi` (**Settings → Environments**).
   Optionally require your approval before each publish.

No API tokens are stored anywhere.

### Each release

1. Bump `version` in `pyproject.toml` (and in `rust/Cargo.toml` if the Rust code changed).
2. If dependencies changed, regenerate `requirements.txt` (section 8).
3. Commit, push, and open a pull request: CI builds every wheel and runs both audits.
4. When CI is green and merged, tag and push:

   ```bash
   git tag v1.0.8
   git push origin v1.0.8
   ```

5. The workflow builds:
   - native wheels for Linux x86_64/aarch64 (glibc and musl), macOS universal2 and Windows x64
   - a pure-Python wheel for every other platform
   - the sdist

   It then runs `cargo audit` and `pip-audit` and publishes everything to PyPI, with
   provenance attestations.

6. Check the release: `pip install --upgrade dStats` in a fresh virtualenv.

Then publish the container image (section 7).

---

## 7. Container image (Docker and Podman)

The `Dockerfile` builds from your checkout in two stages: a builder compiles the wheel,
including the Rust accelerator, and a slim runtime image installs it with the audited
dependency versions from `requirements.txt`. Podman reads the same `Dockerfile`.

### Build

```bash
docker build -t dstats:local .
podman build -t dstats:local .
```

### Run, monitoring Docker

```bash
docker run -d --name dstats \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -p 127.0.0.1:2743:2743 dstats:local
```

### Run, monitoring Podman

```bash
podman run -d --name dstats --security-opt label=disable \
  -v $XDG_RUNTIME_DIR/podman/podman.sock:/run/podman/podman.sock \
  -e DSTATS_ENGINE=podman \
  -p 127.0.0.1:2743:2743 dstats:local
```

`--security-opt label=disable` lets the container use the socket on SELinux systems
(Fedora, RHEL); it's harmless elsewhere.

### Run, monitoring both

Mount each engine's socket where dStats looks for it inside the container:

```bash
podman run -d --name dstats --security-opt label=disable \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $XDG_RUNTIME_DIR/podman/podman.sock:/run/podman/podman.sock \
  -e DSTATS_ENGINE=docker,podman \
  -p 127.0.0.1:2743:2743 dstats:local
```

(`docker run` works the same, without `--security-opt`.) Under rootless Podman, the
container can only open `/var/run/docker.sock` if your user is in the `docker` group and
those groups are passed through: add `--group-add keep-groups` to the command above.

To reach dStats from other machines, set `USE_AUTH=true`, `AUTH_USERNAME` and
`AUTH_PASSWORD`, and publish the port without `127.0.0.1:`.

### Compose

```bash
docker compose up -d --build     # or: podman compose up -d --build
```

Replace the credential placeholders in `docker-compose.yml` first. The UI is on port 6743.

### Publish to Docker Hub (amd64 + arm64)

```bash
# Docker
docker buildx build --platform linux/amd64,linux/arm64 \
  -t arifcse21/dstats:1.0.8 -t arifcse21/dstats:latest --push .

# Podman
podman build --platform linux/amd64,linux/arm64 --manifest dstats-release .
podman manifest push --all dstats-release docker://docker.io/arifcse21/dstats:1.0.8
podman manifest push --all dstats-release docker://docker.io/arifcse21/dstats:latest
```

Cross-building arm64 on an x86 machine needs QEMU emulation (`qemu-user-static`); it's slow
because the Rust accelerator compiles under emulation.

---

## 8. Updating dependencies

Python: `pyproject.toml` sets minimum versions, and `requirements.txt` pins the full audited set
(used by the container image and scanned by Dependabot). After changing dependencies,
regenerate it:

```bash
python -m venv /tmp/dstats-env
DSTATS_PURE_PYTHON=1 /tmp/dstats-env/bin/pip install .
/tmp/dstats-env/bin/pip freeze --exclude dStats   # replace the pins in requirements.txt (keep its header)
pip-audit -r requirements.txt -s osv
```

Rust:

```bash
cd rust
cargo update          # or bump versions in Cargo.toml
cargo clippy --release --locked
cargo audit
```

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| "Cannot reach Docker at unix:///var/run/docker.sock" | Docker isn't running, or your user isn't in the `docker` group (section 3). |
| "Cannot reach Podman …" | `systemctl --user enable --now podman.socket`; check with `podman --remote ps`. |
| Podman tab shows no containers that `sudo podman ps` lists | Those are root's containers; enable the rootful socket or run them rootless. |
| CPU shows N/A under rootless Podman | Rootless stats generally require cgroup v2: `podman info --format '{{.Host.CgroupsVersion}}'` should print `v2`. |
| Page answers `400 Bad Request` | The host name isn't allowed: set `ALLOWED_HOSTS`, or enable auth. |
| Login fails with 403 behind an HTTPS proxy | Set `CSRF_TRUSTED_ORIGINS=https://your.host` and `SECURE_COOKIES=true`. |
| "Too many failed attempts" | 5 failed logins lock that address for 5 minutes; wait it out or restart dStats. |
| `dStats.server: command not found` | Activate the virtualenv, or run `venv/bin/dStats.server`. |
| Rust changes have no effect | Rerun `pip install -e .`; confirm with the `_rust` check in section 2. |
| Graph panel says "Collecting data failed" | Check the server log for the error. |
| Graph panel stays empty | Check the browser console; the page loads its libraries from `/static/dStats/vendor/` on the dStats server itself. |
