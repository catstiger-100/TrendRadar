#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "正在重启 trendradar 容器..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" down trendradar
docker compose -f "$SCRIPT_DIR/docker-compose-build.yml" up -d trendradar --force-recreate
echo "重启完成"
