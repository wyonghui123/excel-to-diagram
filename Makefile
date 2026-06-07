.PHONY: test test-unit test-integration test-api test-performance test-coverage clean

test:
	pytest -v --tb=short

test-unit:
	pytest -m unit -v --tb=short

test-integration:
	pytest -m integration -v --tb=short

test-api:
	pytest -m api -v --tb=short

test-performance:
	pytest meta/tests/performance/ -v --tb=short
	python -m meta.tests.performance.performance_reporter --format markdown

test-coverage:
	pytest --cov=meta --cov-report=html --cov-report=term-missing -v --tb=short

test-all:
	pytest -v --tb=short --cov=meta --cov-report=term-missing

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml 2>/dev/null || true

lint:
	flake8 meta/ --max-line-length=120 --exclude=meta/tests/,meta/core/migrations/

format:
	black meta/ --exclude="meta/tests|meta/core/migrations"
