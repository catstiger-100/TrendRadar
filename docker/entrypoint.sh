#!/bin/bash
set -e

# 等待 PostgreSQL 就绪
if [ -n "${PG_HOST:-}" ]; then
    echo "⏳ 等待 PostgreSQL (${PG_HOST}:${PG_PORT:-5432}) 就绪..."
    for i in $(seq 1 30); do
        if python -c "import psycopg2; psycopg2.connect(host='${PG_HOST}', port=${PG_PORT:-5432}, dbname='${PG_DB:-trendradar}', user='${PG_USER:-trendradar}', password='${PG_PASSWORD:-trendradar}').close()" 2>/dev/null; then
            echo "✅ PostgreSQL 连接成功"
            break
        fi
        echo "   等待中... ($i/30)"
        sleep 2
    done
fi

# 检查配置文件
if [ ! -f "/app/config/config.yaml" ] || [ ! -f "/app/config/frequency_words.txt" ]; then
    echo "❌ 配置文件缺失"
    exit 1
fi

# 保存环境变量
env >> /etc/environment

case "${RUN_MODE:-cron}" in
"once")
    echo "🔄 单次执行"
    exec /usr/local/bin/python -m trendradar
    ;;
"cron")
    # 生成 crontab
    echo "${CRON_SCHEDULE:-*/30 * * * *} cd /app && /usr/local/bin/python -m trendradar" > /tmp/crontab
    
    echo "📅 生成的crontab内容:"
    cat /tmp/crontab

    if ! /usr/local/bin/supercronic -test /tmp/crontab; then
        echo "❌ crontab格式验证失败"
        exit 1
    fi

    # 启动 Web 服务器（如果配置了）
    if [ "${ENABLE_WEBSERVER:-false}" = "true" ]; then
        echo "🌐 启动 Web 服务器..."
        /usr/local/bin/python manage.py start_webserver
    fi

    # 立即执行一次（如果配置了）
    if [ "${IMMEDIATE_RUN:-false}" = "true" ]; then
        echo "▶️ 立即执行一次"
        /usr/local/bin/python -m trendradar
    fi

    echo "⏰ 启动supercronic: ${CRON_SCHEDULE:-*/30 * * * *}"
    echo "🎯 supercronic 将作为 PID 1 运行"

    exec /usr/local/bin/supercronic -passthrough-logs /tmp/crontab
    ;;
*)
    exec "$@"
    ;;
esac
