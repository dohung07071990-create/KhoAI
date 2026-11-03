FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 libgl1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY ai/requirements.txt ./ai-requirements.txt
RUN pip install --no-cache-dir -r ai-requirements.txt
COPY backend ./backend
COPY ai ./ai
COPY frontend ./frontend
COPY public ./public
RUN mkdir -p /app/data/camera_evidence
VOLUME ["/app/data"]
EXPOSE 3000
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-3000}"]
