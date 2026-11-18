#!/usr/bin/env bash
# 本机（macOS）一键启动：Python agent + NestJS 网关 + React 前端
# 用法：./scripts/start-local-mac.sh        Ctrl+C 停止全部
#       RELOAD=1 ./scripts/start-local-mac.sh  代码变更自动重载（开发用）
# 前置：项目根目录已有 .env，且 .venv / 两个 node_modules 已安装
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/Library/Python/3.9/bin:$PATH"

AGENT_PORT="${AGENT_PORT:-8000}"
GATEWAY_PORT="${GATEWAY_PORT:-3111}"   # 3000 常被其他项目占用，默认用 3111
WEB_PORT="${WEB_PORT:-5173}"
# RELOAD=1：agent 用 --reload、网关用 nest --watch，改代码无需手动重启（前端本身就是 HMR）
RELOAD="${RELOAD:-0}"
RELOAD_TAG=""
if [ "$RELOAD" = "1" ]; then RELOAD_TAG=" (reload)"; fi

pids=()
cleanup() {
  echo ""
  echo "正在停止服务..."
  for pid in "${pids[@]:-}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

echo "==> [1/3] 启动 Python agent :$AGENT_PORT$RELOAD_TAG"
if [ "$RELOAD" = "1" ]; then
  # 只监听 app/ 目录，避免 data/、.venv/ 写入触发重启循环
  (cd "$ROOT" && exec .venv/bin/python -m uvicorn app.main:app \
    --host 127.0.0.1 --port "$AGENT_PORT" --reload --reload-dir app) &
else
  (cd "$ROOT" && exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$AGENT_PORT") &
fi
pids+=($!)

for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:$AGENT_PORT/health" >/dev/null 2>&1; then
    echo "    agent 健康检查通过"
    break
  fi
  sleep 1
done

echo "==> [2/3] 启动 NestJS 网关 :$GATEWAY_PORT$RELOAD_TAG"
if [ "$RELOAD" = "1" ]; then
  (cd "$ROOT/form-gateway-nest" && PORT="$GATEWAY_PORT" \
    AI_AGENT_BASE_URL="http://127.0.0.1:$AGENT_PORT" \
    AI_AGENT_TIMEOUT_MS=60000 \
    exec npm run start:dev) &
else
  (cd "$ROOT/form-gateway-nest" && PORT="$GATEWAY_PORT" \
    AI_AGENT_BASE_URL="http://127.0.0.1:$AGENT_PORT" \
    AI_AGENT_TIMEOUT_MS=60000 \
    exec node dist/main.js) &
fi
pids+=($!)

echo "==> [3/3] 启动前端 :$WEB_PORT"
(cd "$ROOT/form-web-react" && exec npm run dev) &
pids+=($!)

echo ""
echo "全部启动：浏览器打开 http://localhost:$WEB_PORT"
echo "按 Ctrl+C 停止全部服务"
wait
