# Build stage: compile dStats (including the Rust accelerator) from this checkout.
FROM python:3.13-trixie AS build

# Before COPY, so this layer is cached and code changes don't reinstall Rust
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH=/root/.cargo/bin:$PATH

WORKDIR /src
COPY . .
RUN pip wheel --no-deps --wheel-dir /wheels .


# Runtime stage: no compilers or Rust toolchain, just the built wheel
FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Listen on all interfaces inside the container; `-p` decides what the host exposes
ENV DSTATS_HOST=0.0.0.0

WORKDIR /dStats

# requirements.txt pins the audited dependency versions
COPY requirements.txt /tmp/requirements.txt
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir -c /tmp/requirements.txt /wheels/*.whl \
    && rm -rf /wheels /tmp/requirements.txt

EXPOSE 2743

# Healthy once the dashboard answers. Podman keeps this only in Docker-format images:
# build with `podman build --format docker`.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:2743/', timeout=5)"]

CMD ["dStats.server"]
