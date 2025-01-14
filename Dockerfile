# Use Python 3.12 slim base image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=dStats.settings

# Set work directory
WORKDIR /app

# Install system dependencies for Graphviz
RUN apt-get update && apt-get install -y \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project files
COPY . .

# Expose the port for the Daphne server
EXPOSE 2743

# Run the application using Daphne
CMD ["daphne", "-b", "0.0.0.0", "-p", "2743", "dStats.asgi:application"]
