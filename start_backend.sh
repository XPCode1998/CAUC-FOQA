#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_SH="${CONDA_SH:-/home/ubuntu/anaconda3/etc/profile.d/conda.sh}"
CONDA_ENV="${CONDA_ENV:-pytorch_django_env}"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

echo "[INFO] 项目根目录: $PROJECT_ROOT"

if [[ ! -f "$PROJECT_ROOT/manage.py" ]]; then
  echo "[ERROR] 未找到 manage.py，请在项目根目录执行此脚本。"
  exit 1
fi

if [[ ! -f "$CONDA_SH" ]]; then
  echo "[ERROR] 未找到 conda 初始化脚本: $CONDA_SH"
  echo "        可通过环境变量 CONDA_SH 覆盖默认路径。"
  exit 1
fi

cd "$PROJECT_ROOT"
source "$CONDA_SH"
conda activate "$CONDA_ENV"

echo "[INFO] 启动后端服务: http://$BACKEND_HOST:$BACKEND_PORT"
exec python manage.py runserver "$BACKEND_HOST:$BACKEND_PORT"