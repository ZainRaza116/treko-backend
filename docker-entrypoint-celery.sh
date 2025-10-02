#!/bin/bash

# Wait for database to be ready
echo "Waiting for database..."
python manage.py wait_for_db

echo "Starting Celery worker..."
celery -A config worker --loglevel=info