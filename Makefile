.PHONY: bootstrap test test-python test-ui api ui dev migrate seed cli format lint clean

bootstrap:
	python -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -r requirements-dev.txt
	cd ui && npm install
	. .venv/bin/activate && PYTHONPATH=packages/kubeops_core:packages/kubeops_cli:control_plane python control_plane/manage.py migrate
	. .venv/bin/activate && PYTHONPATH=packages/kubeops_core:packages/kubeops_cli:control_plane python control_plane/manage.py seed_release_01

migrate:
	. .venv/bin/activate && PYTHONPATH=packages/kubeops_core:packages/kubeops_cli:control_plane python control_plane/manage.py migrate

seed:
	. .venv/bin/activate && PYTHONPATH=packages/kubeops_core:packages/kubeops_cli:control_plane python control_plane/manage.py seed_release_01

api:
	. .venv/bin/activate && PYTHONPATH=packages/kubeops_core:packages/kubeops_cli:control_plane python control_plane/manage.py runserver 0.0.0.0:8000

ui:
	cd ui && npm run dev -- --host 0.0.0.0

cli:
	./scripts/kubeops.sh

test-python:
	. .venv/bin/activate && PYTHONPATH=packages/kubeops_core:packages/kubeops_cli:control_plane pytest

test-ui:
	cd ui && npm run build

test: test-python test-ui

lint:
	. .venv/bin/activate && PYTHONPATH=packages/kubeops_core:packages/kubeops_cli:control_plane ruff check packages control_plane tests
	. .venv/bin/activate && PYTHONPATH=packages/kubeops_core:packages/kubeops_cli:control_plane mypy packages/kubeops_core/kubeops_core
	cd ui && npm run lint

format:
	. .venv/bin/activate && ruff format packages control_plane tests
	cd ui && npm run format

clean:
	rm -rf .venv artifacts .pytest_cache .mypy_cache .ruff_cache
	rm -rf ui/node_modules ui/dist
