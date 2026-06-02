# ModelForge-Swarm sandbox execution image (spec 35 docker/sandbox).
# Minimal Python 3.12 image with the MVP scientific stack and a non-root user.
FROM python:3.12-slim

# Non-root user (spec 20.4). UID 1000 matches the --user flag in the runner.
RUN groupadd -g 1000 sandbox && useradd -m -u 1000 -g 1000 sandbox \
    && mkdir -p /workspace/input /workspace/src /workspace/output /workspace/logs \
    && chown -R sandbox:sandbox /workspace

# coreutils provides `timeout` used to bound in-container runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends coreutils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

ENV MPLBACKEND=Agg \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1

USER sandbox
WORKDIR /workspace/src
