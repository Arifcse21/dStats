FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Listen on all interfaces inside the container; `-p` decides what the host exposes
ENV DSTATS_HOST=0.0.0.0

WORKDIR /dStats

RUN apt-get update && apt-get install -y \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

RUN pip install dStats


EXPOSE 2743

CMD ["dStats.server"]
