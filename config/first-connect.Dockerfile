FROM quay.io/jupyter/pytorch-notebook:cuda12-notebook-7.5.5
# Source-only frozen archive in an isolated build context; no .local/, keys or weights.
ADD gpu-service.tar.gz /opt/lighttry/
USER jovyan
EXPOSE 8443 443
# Provisioned read-only runtime secrets; never bake private keys into image layers.
ENTRYPOINT ["python", "-B", "/opt/lighttry/start.py", "--first-connect-agent", "--config", "/run/lighttry/first-connect.json"]
