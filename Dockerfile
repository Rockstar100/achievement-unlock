FROM python:3.11-slim-bookworm

WORKDIR /app

# Cron for in-container daily pipeline (shares /data disk with dashboard)
RUN apt-get update \
    && apt-get install -y --no-install-recommends cron \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-render.txt requirements-cron.txt ./
RUN pip install --no-cache-dir -r requirements-render.txt -r requirements-cron.txt

COPY . .

RUN chmod +x scripts/render_start.sh \
    && echo "30 2 * * * root cd /app && /usr/local/bin/python scripts/run_render_pipeline.py >> /var/log/pet-trend-pipeline.log 2>&1" \
       > /etc/cron.d/pet-trend \
    && chmod 0644 /etc/cron.d/pet-trend

ENV PYTHONUNBUFFERED=1 \
    DASHBOARD_HOST=0.0.0.0 \
    DATA_DIR=/data \
    ENVIRONMENT=staging \
    AMAZON_USE_PLAYWRIGHT=never

EXPOSE 10000

CMD ["/bin/sh", "scripts/render_start.sh"]
