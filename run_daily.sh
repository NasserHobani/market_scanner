#!/usr/bin/env bash
# مسح يومي تلقائي. للتفعيل:  crontab -e
#   0 6 * * *  /path/to/market-scanner/run_daily.sh >> /tmp/scanner.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"

export TELEGRAM_TOKEN="${TELEGRAM_TOKEN:-}"
export TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

python3 -m scanner.run --market crypto --html --notify --quiet
python3 -m scanner.run --market us     --html --notify --quiet
python3 -m scanner.run --market saudi  --html --notify --quiet
