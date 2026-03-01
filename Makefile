UV_CACHE_DIR ?= .uv-cache
COVERAGE_FILE ?= .coverage
PYTHONPATH ?= src

.PHONY: test
test:
	@PYTHONPATH=$(PYTHONPATH) UV_CACHE_DIR=$(UV_CACHE_DIR) COVERAGE_FILE=$(COVERAGE_FILE) uv run --no-sync python -m coverage run -m scripts.run_tests
	@PYTHONPATH=$(PYTHONPATH) UV_CACHE_DIR=$(UV_CACHE_DIR) COVERAGE_FILE=$(COVERAGE_FILE) uv run --no-sync python -m coverage report -m --fail-under=95 --include="src/tickertrail/cli.py" >/dev/null
