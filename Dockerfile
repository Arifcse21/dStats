# Dockerfile
FROM python:3-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=dStats.settings

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Expose port
EXPOSE 2743

# Run the application
CMD ["python", "manage.py", "runserver", "0.0.0.0:2743"]
