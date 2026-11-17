#!/usr/bin/env bash
set -Eeuo pipefail

# Run from any directory: setup always targets this repository.
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [[ ! -f requirements.txt ]]; then
  echo "ERROR: requirements.txt not found in $PROJECT_DIR" >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "ERROR: This setup requires Raspberry Pi OS / Debian with apt-get." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found." >&2
  exit 1
fi

if [[ $(id -u) -eq 0 ]]; then
  APT=(apt-get)
elif command -v sudo >/dev/null 2>&1; then
  APT=(sudo apt-get)
else
  echo "ERROR: apt packages require sudo/root. Run on Raspberry Pi OS with sudo available." >&2
  exit 1
fi

echo '[1/6] Installing system packages (apt)...'
"${APT[@]}" update
"${APT[@]}" install -y \
  python3-venv python3-pip

echo '[2/6] Creating virtual environment...'
if [[ ! -d .venv ]]; then
  python3 -m venv --system-site-packages .venv
elif [[ ! -x .venv/bin/python ]]; then
  echo 'ERROR: .venv exists but has no executable Python. Rename/delete .venv and rerun.' >&2
  exit 1
else
  if ! grep -Eq '^include-system-site-packages = true$' .venv/pyvenv.cfg; then
    echo 'ERROR: Existing .venv lacks system-site-packages.' >&2
    echo 'Rename/delete .venv and rerun setup.sh to recreate it.' >&2
    exit 1
  fi
  echo 'Using existing .venv.'
fi

echo '[3/6] Installing project pip requirements...'
.venv/bin/python -m pip install -r requirements.txt

echo '[4/6] Checking imports...'
.venv/bin/python - <<'PY'
import sqlite3
import fastapi
import pandas
import tuya_iot
import webdav3
import uvicorn
print('OK: sqlite3, fastapi, pandas, tuya_iot, webdav3, uvicorn import successfully')
PY

echo '[5/6] Installing the service data-api.service...'
sudo cp data-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now data-api.service
echo 'Waiting for service to initialize...'

for i in {1..10}; do
    if curl -fsS http://localhost:8000/status > /dev/null; then
        echo 'FastAPI is ready!'
        break
    fi
    sleep 1
done

sudo systemctl status data-api.service --no-pager

echo '[6/6] Installing crontabs for scripts...'
# Cron jobs
CRON_BWSYNC="0 8 * * 1 /home/poim/pi_sensor/.venv/bin/python /home/poim/pi_sensor/crontab-scripts/bwsync_upload.py command arg >> /home/poim/pi_sensor/crontab-scripts/cron_bwsync.log 2>&1"
CRON_STORAGE="0 8 * * 1 /home/poim/pi_sensor/.venv/bin/python /home/poim/pi_sensor/crontab-scripts/storage_monitor.py command arg >> /home/poim/pi_sensor/crontab-scripts/cron_storage.log 2>&1"
CRON_LOGGER="0,30 * * * * /home/poim/pi_sensor/.venv/bin/python /home/poim/pi_sensor/crontab-scripts/continuous_data_logger.py command arg >> /home/poim/pi_sensor/crontab-scripts/cron_logger.log 2>&1"

# Install cron jobs for the poim user
# Preserve existing jobs and avoid duplicates
EXISTING_CRON=$(sudo crontab -u poim -l 2>/dev/null || true)

{
    printf '%s\n' "$EXISTING_CRON" |
        grep -v -F '/home/poim/pi_sensor/crontab-scripts/bwsync_upload.py' |
        grep -v -F '/home/poim/pi_sensor/crontab-scripts/storage_monitor.py' |
        grep -v -F '/home/poim/pi_sensor/crontab-scripts/continuous_data_logger.py' || true

    echo "$CRON_BWSYNC"
    echo "$CRON_STORAGE"
    echo "$CRON_LOGGER"

} | sudo crontab -u poim -

# Enable and start cron
sudo systemctl enable --now cron

echo 'Cron jobs installed successfully!'
sudo crontab -u poim -l

echo
echo 'Setup complete.'
