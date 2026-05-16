#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

echo "[INFO] 前端目录: $FRONTEND_DIR"

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "[ERROR] 未找到 frontend/package.json，请确认前端目录存在。"
  exit 1
fi

cd "$FRONTEND_DIR"
echo "[INFO] 启动前端服务: http://$FRONTEND_HOST:$FRONTEND_PORT"
exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"