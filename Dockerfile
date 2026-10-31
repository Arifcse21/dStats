# Build stage: compile dStats (including the Rust accelerator) from this checkout
FROM python:3.13-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH=/root/.cargo/bin:$PATH

WORKDIR /src
COPY . .
RUN pip wheel --no-deps --wheel-dir /wheels .


# Runtime stage: no compilers or Rust toolchain, just the built wheel
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Listen on all interfaces inside the container; `-p` decides what the host exposes
ENV DSTATS_HOST=0.0.0.0

WORKDIR /dStats

RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt pins the audited dependency versions
COPY requirements.txt /tmp/requirements.txt
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir -c /tmp/requirements.txt /wheels/*.whl \
    && rm -rf /wheels /tmp/requirements.txt

EXPOSE 2743

CMD ["dStats.server"]
