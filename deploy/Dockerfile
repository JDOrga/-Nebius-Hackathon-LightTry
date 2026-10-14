FROM python:3.14-slim
WORKDIR /opt/lighttry
COPY requirements-cpu.txt ./
RUN pip install --no-cache-dir -r requirements-cpu.txt \
    && useradd --uid 10001 --create-home lighttry \
    && mkdir -p /var/lib/lighttry && chown lighttry:lighttry /var/lib/lighttry
COPY start.py ./
COPY project/ ./project/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LIGHTTRY_DATA_ROOT=/var/lib/lighttry
USER lighttry
VOLUME ["/var/lib/lighttry"]
EXPOSE 8080
CMD ["python", "-X", "utf8", "-B", "start.py", "--service"]
