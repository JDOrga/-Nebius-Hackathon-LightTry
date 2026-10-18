ARG PYTHON_IMAGE=python:3.14.0-slim-bookworm@sha256:d13fa0424035d290decef3d575cea23d1b7d5952cdf429df8f5542c71e961576
FROM ${PYTHON_IMAGE}
LABEL org.opencontainers.image.title="LightTry CPU" org.opencontainers.image.version="2026.10.18-cpu.2"
WORKDIR /opt/lighttry
RUN apt-get update && apt-get install --no-install-recommends -y openssh-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-cpu.txt ./
ARG WHEELHOUSE=
RUN if [ -n "$WHEELHOUSE" ]; then pip install --no-cache-dir --no-index --find-links "$WHEELHOUSE" -r requirements-cpu.txt; \
    else pip install --no-cache-dir -r requirements-cpu.txt; fi \
    && useradd --uid 10001 --create-home lighttry \
    && mkdir -p /var/lib/lighttry && chown lighttry:lighttry /var/lib/lighttry
COPY start.py ./
COPY project/ ./project/
COPY scripts/weights.py ./scripts/weights.py
COPY cloud/cli_bridge.py cloud/remote_probe.py ./cloud/
COPY manifests/ ./manifests/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LIGHTTRY_DATA_ROOT=/var/lib/lighttry
USER lighttry
VOLUME ["/var/lib/lighttry"]
EXPOSE 8080
CMD ["python", "-X", "utf8", "-B", "start.py", "--service"]
