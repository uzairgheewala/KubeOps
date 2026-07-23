FROM python:3.13-slim AS runtime
WORKDIR /workspace
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/packages/kubeops_core:/workspace/packages/kubeops_pack_sdk:/workspace/packages/kubeops_cli:/workspace/control_plane
RUN groupadd --system kubeops && useradd --system --gid kubeops --home /workspace kubeops
COPY packages/kubeops_core /workspace/packages/kubeops_core
COPY packages/kubeops_cli /workspace/packages/kubeops_cli
COPY packages/kubeops_pack_sdk /workspace/packages/kubeops_pack_sdk
COPY control_plane /workspace/control_plane
COPY requirements-runtime.txt /workspace/requirements-runtime.txt
RUN pip install --no-cache-dir -r requirements-runtime.txt
COPY scenarios /workspace/scenarios
COPY profiles /workspace/profiles
COPY lifecycle /workspace/lifecycle
COPY policies /workspace/policies
COPY packs /workspace/packs
COPY lab/fixtures /workspace/lab/fixtures
COPY environments /workspace/environments
COPY fleets /workspace/fleets
COPY governance /workspace/governance
COPY trust /workspace/trust
RUN mkdir -p /workspace/artifacts /workspace/operations /workspace/backups && chown -R kubeops:kubeops /workspace
USER kubeops
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/system/status', timeout=3)"
CMD ["gunicorn", "config.wsgi:application", "--chdir", "/workspace/control_plane", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
