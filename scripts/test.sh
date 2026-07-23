#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
export PYTHONPATH="$PWD/packages/kubeops_core:$PWD/packages/kubeops_pack_sdk:$PWD/packages/kubeops_cli:$PWD/control_plane${PYTHONPATH:+:$PYTHONPATH}"
pytest
(cd ui && npm run build)
