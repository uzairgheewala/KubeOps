#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
(cd ui && npm install)
export PYTHONPATH="$PWD/packages/kubeops_core:$PWD/packages/kubeops_pack_sdk:$PWD/packages/kubeops_cli:$PWD/control_plane${PYTHONPATH:+:$PYTHONPATH}"
python control_plane/manage.py migrate
python control_plane/manage.py seed_release_01
python control_plane/manage.py seed_release_02
python control_plane/manage.py seed_release_04
python control_plane/manage.py seed_release_05
python control_plane/manage.py seed_release_10
printf '\nKubeOps Release 1.0 is bootstrapped.\n'
printf 'Run ./scripts/dev.sh to start API and UI.\n'
