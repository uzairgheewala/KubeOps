FROM python:3.13-slim
WORKDIR /workspace
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/workspace/packages/kubeops_core:/workspace/packages/kubeops_cli:/workspace/control_plane
COPY packages/kubeops_core /workspace/packages/kubeops_core
COPY packages/kubeops_cli /workspace/packages/kubeops_cli
COPY control_plane /workspace/control_plane
COPY requirements-runtime.txt /workspace/requirements-runtime.txt
RUN pip install --no-cache-dir -r requirements-runtime.txt
COPY scenarios /workspace/scenarios
COPY profiles /workspace/profiles
COPY lifecycle /workspace/lifecycle
COPY policies /workspace/policies
COPY lab/fixtures /workspace/lab/fixtures
COPY environments /workspace/environments
EXPOSE 8000
