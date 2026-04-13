#!/usr/bin/env bash
# 初始化虚拟环境并安装依赖（需已安装 https://github.com/astral-sh/uv ）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[PTAgent] 使用 uv 创建/更新虚拟环境并安装 requirements.txt ..."
uv venv
uv pip install -r requirements.txt

echo "[PTAgent] 完成。请: source .venv/bin/activate  然后  ./scripts/run-backend.sh"

