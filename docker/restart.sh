#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose-build.yml"
ENV_FILE="$SCRIPT_DIR/.env"

echo "=== TrendRadar Docker 重启脚本 ==="

# 1. 检查依赖
if [ ! -f "$COMPOSE_FILE" ]; then
  echo "❌ Compose 文件不存在: $COMPOSE_FILE"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ 环境变量文件不存在: $ENV_FILE"
  exit 1
fi

DOCKER_COMPOSE="docker compose --env-file $ENV_FILE -f $COMPOSE_FILE"

# 2. 强制停止并彻底移除旧容器和镜像
echo ""
echo "🛑 停止并移除旧容器、镜像..."
$DOCKER_COMPOSE down --rmi local --remove-orphans || true

# 兜底：确保没有残留的冲突容器
for name in trendradar trendradar-mcp; do
  if docker ps -a --format '{{.Names}}' | grep -q "^${name}$"; then
    docker rm -f "$name" || true
  fi
done

echo "✅ 旧容器已清理"

# 3. 构建前端 console
CONSOLE_DIR="$SCRIPT_DIR/../console"
echo ""
echo "📦 构建前端 console..."
if [ -d "$CONSOLE_DIR" ]; then
  cd "$CONSOLE_DIR"
  npm install --quiet
  npm run build
  cd "$SCRIPT_DIR"
  echo "✅ console 构建完成"
else
  echo "⚠️  console 目录不存在，跳过前端构建"
fi

# 4. 从本地源码构建镜像并启动
echo ""
echo "🔨 构建镜像（利用缓存，依赖不重新安装）..."
$DOCKER_COMPOSE build

echo ""
echo "🚀 启动服务..."
$DOCKER_COMPOSE up -d

# 5. 显示状态
echo ""
echo "✅ 重启完成，当前状态："
$DOCKER_COMPOSE ps
