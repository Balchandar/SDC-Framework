.PHONY: install dev test lint example build clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	python3 -m pytest -q

example:
	cd examples/customer-api && sdc build

build:
	sdc build

inspect:
	cd examples/customer-api && sdc inspect

clean:
	rm -rf build/ examples/*/.build examples/*/dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
