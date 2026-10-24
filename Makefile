# Booklyfi — Makefile
# Upotreba: make <target>

PYTHON := venv/bin/python3
PYTEST := venv/bin/python3 -m pytest
PYFLAKES := /usr/local/bin/pyflakes

.PHONY: help test golden lint lint-strict all clean

help:
	@echo "Booklyfi make targets:"
	@echo "  make test         — pytest tests/ (94 testova)"
	@echo "  make golden       — pytest tests/golden/ (smoke + determinizam)"
	@echo "  make lint         — pyflakes sve *.py (informativno, ne fail)"
	@echo "  make lint-strict  — pyflakes, fail na warning"
	@echo "  make all          — lint + test + golden"
	@echo "  make clean        — ocisti __pycache__ i .pytest_cache"

test:
	$(PYTEST) tests/ -q

golden:
	$(PYTEST) tests/golden/ -v

lint:
	@echo "─── pyflakes (informativno) ───"
	@$(PYFLAKES) \
		config/*.py core/*.py core/**/*.py network/*.py \
		processing/*.py epub/*.py analysis/*.py utils/*.py \
		api/*.py api/routes/*.py tests/*.py tests/**/*.py \
		main.py run.py app.py 2>&1 | head -50 || true
	@echo "─── (puno izvjestaja: make lint-strict) ───"

lint-strict:
	@echo "─── pyflakes (strict) ───"
	@$(PYFLAKES) \
		config/*.py core/*.py core/**/*.py network/*.py \
		processing/*.py epub/*.py analysis/*.py utils/*.py \
		api/*.py api/routes/*.py \
		main.py run.py app.py 2>&1

all: lint test golden
	@echo ""
	@echo "✅ Svi targeti prosli"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
