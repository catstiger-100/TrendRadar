#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose-build.yml"
ENV_FILE="$SCRIPT_DIR/.env"
SERVICE="${1:-trendradar}"

echo "=== TrendRadar Docker 重建脚本 ==="
echo "服务: $SERVICE"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "❌ Compose 文件不存在: $COMPOSE_FILE"
  exit 1
fi

COMPOSE_ARGS=(-f "$COMPOSE_FILE")
if [ -f "$ENV_FILE" ]; then
  COMPOSE_ARGS=(--env-file "$ENV_FILE" "${COMPOSE_ARGS[@]}")
else
  echo "⚠️ 未找到环境变量文件，继续使用当前环境变量: $ENV_FILE"
fi

echo ""
echo "🔨 构建镜像..."
docker compose "${COMPOSE_ARGS[@]}" build "$SERVICE"

echo ""
echo "🚀 重建并启动容器..."
docker compose "${COMPOSE_ARGS[@]}" up -d --no-deps --force-recreate "$SERVICE"

echo ""
echo "✅ 完成，当前状态："
docker compose "${COMPOSE_ARGS[@]}" ps "$SERVICE"
