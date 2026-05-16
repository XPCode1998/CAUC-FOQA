#!/usr/bin/env bash

set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

kill_by_port() {
  local port="$1"
  local label="$2"
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' | xargs -r echo || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -n tcp "$port" 2>/dev/null | tr '\n' ' ' | xargs -r echo || true)"
  elif command -v ss >/dev/null 2>&1; then
    pids="$(ss -lptn "sport = :$port" 2>/dev/null | awk -F 'pid=' 'NR>1 {split($2,a,",|") ; if (a[1] ~ /^[0-9]+$/) print a[1]}' | sort -u | tr '\n' ' ' | xargs -r echo || true)"
  else
    echo "[WARN] 无法检查端口 $port（未安装 lsof/fuser/ss）。"
    return 1
  fi

  if [[ -z "$pids" ]]; then
    echo "[INFO] $label 端口 $port 未发现监听进程。"
    return 0
  fi

  echo "[INFO] 终止 $label 进程 (port=$port, pid=$pids)"
  kill $pids 2>/dev/null || true
  sleep 1

  local alive=""
  for pid in $pids; do
    if kill -0 "$pid" 2>/dev/null; then
      alive+="$pid "
    fi
  done

  if [[ -n "$alive" ]]; then
    echo "[WARN] 进程仍在运行，执行强制终止: $alive"
    kill -9 $alive 2>/dev/null || true
  fi

  echo "[DONE] $label 停止完成。"
}

echo "[INFO] 开始停止前后端服务..."
kill_by_port "$BACKEND_PORT" "后端"
kill_by_port "$FRONTEND_PORT" "前端"
echo "[DONE] 停止脚本执行完毕。"