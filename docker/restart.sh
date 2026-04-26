#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose-build.yml"
ENV_FILE="$SCRIPT_DIR/.env"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "❌ Compose 文件不存在: $COMPOSE_FILE"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ 环境变量文件不存在: $ENV_FILE"
  exit 1
fi

echo "正在重新构建并重启 TrendRadar Docker 服务..."
echo "Compose: $COMPOSE_FILE"
echo "Env:     $ENV_FILE"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build --force-recreate

echo "重启完成"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps
