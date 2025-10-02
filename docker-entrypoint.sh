#!/bin/bash

# Wait for database to be ready
echo "Waiting for database..."
python manage.py wait_for_db

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate

# Collecting Static Files
python manage.py collectstatic --noinput

# Start server
echo "Starting server..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --worker-class gthread --threads 3 --timeout 60 config.wsgi:application