# Makefile for Django project with Poetry

# Variables
POETRY = poetry
PYTHON = $(POETRY) run python
MANAGE = $(PYTHON) manage.py
PORT = 8000

# Default target
.PHONY: help
help:
	@echo "Available commands:"
	@echo "  make install        - Install dependencies with Poetry"
	@echo "  make init           - Initialize Django project (migrations, superuser)"
	@echo "  make migrate        - Run Django migrations"
	@echo "  make makemigrations - Create new Django migrations"
	@echo "  make runserver      - Start Django development server"
	@echo "  make test           - Run tests with coverage"
	@echo "  make shell          - Start Django shell"
	@echo "  make clean          - Remove temporary files"
	@echo "  make lint           - Run linter (flake8)"
	@echo "  make format         - Run code formatter (black)"

# Install dependencies
.PHONY: install
install:
	$(POETRY) install

# Initialize project
.PHONY: init
init: migrate createsuperuser
	@echo "Project initialized"

# Run migrations
.PHONY: migrate
migrate:
	$(MANAGE) migrate

# Create migrations
.PHONY: makemigrations
makemigrations:
	$(MANAGE) makemigrations

# Create superuser
.PHONY: createsuperuser
createsuperuser:
	$(MANAGE) createsuperuser

# Run development server
.PHONY: runserver
runserver:
	$(MANAGE) runserver $(PORT)

# Run tests
.PHONY: test
test:
	$(POETRY) run pytest --cov=./ --cov-report=html

# Start Django shell
.PHONY: shell
shell:
	$(MANAGE) shell

# Clean temporary files
.PHONY: clean
clean:
	find . -name '__pycache__' -exec rm -rf {} +
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -f .coverage

# Run linter
.PHONY: lint
lint:
	$(POETRY) run flake8 .

# Run formatter
.PHONY: format
format:
	$(POETRY) run black .
	$(POETRY) run isort .