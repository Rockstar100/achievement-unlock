#!/bin/sh
set -e
cd /app
python scripts/render_bootstrap_data.py
# Background cron for daily refresh (02:30 UTC ≈ 8:00 IST)
if [ -f /etc/cron.d/pet-trend ]; then
  cron
  echo "Cron started (daily pipeline at 02:30 UTC)"
fi
exec python scripts/serve_dashboard.py
