#!/bin/bash
set -euo pipefail

# Colors for better readability
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Waiting for database...${NC}"
python manage.py wait_for_db

echo -e "${YELLOW}Applying database migrations...${NC}"
python manage.py migrate --noinput

echo -e "${YELLOW}Collecting static files...${NC}"
python manage.py collectstatic --noinput

echo -e "${GREEN}Starting Gunicorn server...${NC}"
exec gunicorn \
  --bind 0.0.0.0:8000 \
  --workers "${WORKERS:-3}" \
  --worker-class gthread \
  --threads "${THREADS:-3}" \
  --timeout "${TIMEOUT:-60}" \
  config.wsgi:application
