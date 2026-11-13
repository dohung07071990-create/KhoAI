FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 KHOAI_AI_DEVICE=cpu KHOAI_ZONE_FILE=/app/data/zone.json FORWARDED_ALLOW_IPS=127.0.0.1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 libgl1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY ai/requirements.txt ./ai-requirements.txt
# Install CPU wheels explicitly; ultralytics then reuses the installed torch runtime.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r ai-requirements.txt
COPY requirements-webrtc.txt ./
RUN pip install --no-cache-dir -r requirements-webrtc.txt
COPY backend ./backend
COPY ai ./ai
COPY config ./config
COPY frontend ./frontend
COPY public ./public
COPY VERSION.txt ./VERSION.txt
RUN mkdir -p /app/data/camera_evidence && cp ai/zone.json.example /app/data/zone.json && useradd --system --uid 10001 --create-home khoai && chown -R khoai:khoai /app
USER khoai
VOLUME ["/app/data"]
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/api/health',timeout=3).read()"
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-3000} --proxy-headers --forwarded-allow-ips ${KHOAI_TRUSTED_PROXY_IPS:-127.0.0.1}"]
