FROM python:3.13

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=dStats.settings

WORKDIR /app

# RUN apt-get update && apt-get install -y \
#     graphviz \
#     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 2743

CMD ["daphne", "-b", "0.0.0.0", "-p", "2743", "dStats.asgi:application"]
