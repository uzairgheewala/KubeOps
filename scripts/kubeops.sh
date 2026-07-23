#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .venv/bin/activate ]]; then source .venv/bin/activate; fi
export PYTHONPATH="$PWD/packages/kubeops_core:$PWD/packages/kubeops_pack_sdk:$PWD/packages/kubeops_cli:$PWD/control_plane${PYTHONPATH:+:$PYTHONPATH}"
exec python -m kubeops_cli.main "$@"
