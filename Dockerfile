FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-impress fonts-nanum \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV STORAGE=supabase PORT=10000
CMD gunicorn --workers 1 --threads 2 --timeout 180 --bind 0.0.0.0:${PORT} app:app
