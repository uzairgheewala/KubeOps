#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
export PYTHONPATH="$PWD/packages/kubeops_core:$PWD/packages/kubeops_cli:$PWD/control_plane${PYTHONPATH:+:$PYTHONPATH}"
trap 'kill 0' EXIT
python control_plane/manage.py runserver 0.0.0.0:8000 &
(cd ui && npm run dev -- --host 0.0.0.0) &
wait
