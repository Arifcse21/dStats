# Running dStats with `docker run` / `podman run`

The same four scenarios as [docker-compose.yml](docker-compose.yml), as single
self-contained commands for when you don't use Compose. Each one matches its Compose
profile: image, container name, restart policy, published port, socket mounts and
security options. The healthcheck is built into the image (every 30s, the dashboard must
answer), so it needs no flags.

| Scenario | Compose profile | Section |
|---|---|---|
| Monitor Docker | `docker` | [1](#1-monitor-docker) |
| Monitor Podman (rootless or rootful) | `podman` | [2](#2-monitor-podman) |
| Monitor both, dStats run by Docker | `both` | [3](#3-monitor-both-run-by-docker) |
| Monitor both, dStats run by rootless Podman | `both-rootless` | [4](#4-monitor-both-run-by-rootless-podman) |

Run one scenario at a time: they all use the container name `dstats` and port 2743.
Open the dashboard at http://localhost:2743.

---

## 1. Monitor Docker

```bash
docker run -d --name dstats \
  --restart unless-stopped \
  -e DSTATS_ENGINE=docker \
  -p 127.0.0.1:2743:2743 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  arifcse21/dstats:latest
```

## 2. Monitor Podman

Enable Podman's API socket on the host first (no `sudo` for rootless):
`systemctl --user enable --now podman.socket`

```bash
podman run -d --name dstats \
  --restart unless-stopped \
  -e DSTATS_ENGINE=podman \
  -p 127.0.0.1:2743:2743 \
  -v /run/user/$(id -u)/podman/podman.sock:/run/podman/podman.sock \
  --security-opt label=disable \
  docker.io/arifcse21/dstats:latest
```

For rootful Podman, mount `/run/podman/podman.sock` instead and run it with
`sudo podman`. `--security-opt label=disable` lets the container use the socket on
SELinux systems (Fedora, RHEL) and is harmless elsewhere.

## 3. Monitor both, run by Docker

The container runs as root, so it can open both sockets. Switch engines in the navbar.

```bash
docker run -d --name dstats \
  --restart unless-stopped \
  -e DSTATS_ENGINE=docker,podman \
  -p 127.0.0.1:2743:2743 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /run/user/$(id -u)/podman/podman.sock:/run/podman/podman.sock \
  --security-opt label=disable \
  arifcse21/dstats:latest
```

## 4. Monitor both, run by rootless Podman

The Docker socket belongs to the host's `docker` group. `--group-add keep-groups` passes
your user's groups into the container so it can open it. Two requirements:

- Your user is in the `docker` group in the current session (`id -nG` shows `docker`).
- Podman uses the **crun** runtime: `podman info --format '{{.Host.OCIRuntime.Name}}'`
  must print `crun`. With `runc`, `keep-groups` is silently ignored and the Docker tab
  shows "Cannot reach Docker". Install crun (Fedora has it by default; Arch:
  `sudo pacman -S crun`) and Podman picks it up. If you can't, use scenario 3 instead.

```bash
podman run -d --name dstats \
  --restart unless-stopped \
  -e DSTATS_ENGINE=docker,podman \
  -p 127.0.0.1:2743:2743 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /run/user/$(id -u)/podman/podman.sock:/run/podman/podman.sock \
  --security-opt label=disable \
  --group-add keep-groups \
  docker.io/arifcse21/dstats:latest
```

---

## Options

Add any of these to a command above, before the image name.

| Flag | Effect |
|---|---|
| `-e USE_AUTH=true -e AUTH_USERNAME=admin -e AUTH_PASSWORD=change-me` | Require a login. Do this before opening dStats to the network. |
| `-p 0.0.0.0:2743:2743` (instead of `-p 127.0.0.1:2743:2743`) | Reachable from other machines. Only together with the login. |
| `-p 127.0.0.1:8080:2743` | Another host port; the dashboard is then on http://localhost:8080. |
| `-e ALLOWED_HOSTS=stats.example.com` | Only answer to these host names (comma-separated). |
| `-e CSRF_TRUSTED_ORIGINS=https://stats.example.com -e SECURE_COOKIES=true` | Behind an HTTPS reverse proxy. |
| `-e SECRET_KEY=<long random string>` | Stay logged in across restarts. Generate one: `python -c "import secrets; print(secrets.token_urlsafe(50))"` |

For example, scenario 1 with a login, open to the network:

```bash
docker run -d --name dstats \
  --restart unless-stopped \
  -e DSTATS_ENGINE=docker \
  -e USE_AUTH=true -e AUTH_USERNAME=admin -e AUTH_PASSWORD=change-me \
  -p 0.0.0.0:2743:2743 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  arifcse21/dstats:latest
```

---

## Everyday commands

Use `podman` instead of `docker` if Podman runs the container.

| Task | Command |
|---|---|
| Follow the logs | `docker logs -f dstats` |
| Health status | `docker inspect --format '{{.State.Health.Status}}' dstats` |
| Stop and remove | `docker rm -f dstats` |
| Update to the latest image | `docker pull arifcse21/dstats:latest`, then `docker rm -f dstats` and run the command again |
| Change an option | `docker rm -f dstats`, then run the command again with the new flags |

### Build the image from this checkout

```bash
docker build --network host -t dstats:local .
# or
podman build --network host --format docker -t localhost/dstats:local .
```

Then use `dstats:local` (Docker) or `localhost/dstats:local` (Podman) as the image name in
the commands above. `--format docker` keeps the image's healthcheck: Podman's default
image format has no place for it and silently drops it.

### Start automatically with rootless Podman (Quadlet)

`--restart unless-stopped` brings the container back when **Docker** restarts. Rootless
Podman has no daemon to do that; let systemd run it instead with a Quadlet file
(`podman generate systemd` still exists but is deprecated). This one is scenario 2;
remove the container started by hand first (`podman rm -f dstats`).

Save as `~/.config/containers/systemd/dstats.container`:

```ini
[Unit]
Description=dStats container monitor

[Container]
ContainerName=dstats
Image=docker.io/arifcse21/dstats:latest
Environment=DSTATS_ENGINE=podman
PublishPort=127.0.0.1:2743:2743
# %t = your runtime directory, /run/user/<uid>
Volume=%t/podman/podman.sock:/run/podman/podman.sock
SecurityLabelDisable=true

[Service]
Restart=always

[Install]
WantedBy=default.target
```

For scenario 4 (both engines; needs crun, see section 4), change the engine and add the
Docker socket and groups:

```ini
Environment=DSTATS_ENGINE=docker,podman
Volume=/var/run/docker.sock:/var/run/docker.sock
GroupAdd=keep-groups
```

Options from the table above become `Environment=KEY=value` lines (one per setting) and
`PublishPort=` for the port.

Then:

```bash
systemctl --user daemon-reload
systemctl --user start dstats       # starts now, and at every login from now on
systemctl --user status dstats
journalctl --user -u dstats -f      # logs
loginctl enable-linger "$USER"      # optional: start at boot, without logging in
```

Quadlet units are enabled by their `[Install]` section, so `systemctl --user enable` isn't
needed (and reports an error). To remove it: `systemctl --user stop dstats`, delete the
file, `systemctl --user daemon-reload`.
