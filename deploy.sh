#!/usr/bin/env bash
# ==============================================================================
# WeCom Robot - 一键自动化部署脚本 (方案 A)
# 用法:
#   ./deploy.sh "提交说明"
# 功能:
#   1. 自动提交并推送到 GitHub 仓库 (https://github.com/AiiluoChen/WecomBot.git)
#   2. 如果配置了阿里云服务器 IP，自动通过 SSH 让服务器拉取最新代码并重启服务
# ==============================================================================

set -e

# 进入项目根目录
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

# 获取提交信息
MSG="${1:-update: $(date '+%Y-%m-%d %H:%M:%S')}"

echo "========================================================"
echo "📦 1. 正在将代码推送到 GitHub..."
echo "========================================================"

git add .
# 如果没有改动则跳过 commit
if git diff-index --quiet HEAD -- 2>/dev/null; then
    echo "ℹ️  没有检测到需要提交的代码变动。"
else
    git commit -m "$MSG"
fi

# 推送到当前分支
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'main')"
git push -u origin "$CURRENT_BRANCH"
echo "✅ GitHub 代码推送成功！"

# 读取服务器 IP (优先从环境变量或 .env 中读取，支持 SERVER_IP / TENCENT_SERVER_IP / ALIYUN_SERVER_IP)
SERVER_IP=""
if [ -f ".env" ]; then
    SERVER_IP=$(grep -E "^(SERVER_IP|TENCENT_SERVER_IP|ALIYUN_SERVER_IP)=" .env | head -n1 | cut -d '=' -f2 | tr -d ' ' || true)
fi
SERVER_IP="${SERVER_IP:-129.28.42.58}"

echo ""
echo "========================================================"
echo "🚀 2. 检查云服务器部署状态..."
echo "========================================================"

if [ -n "$SERVER_IP" ]; then
    echo "📡 正在连接云服务器 [$SERVER_IP] 执行热更新..."
    rsync -avz --exclude '.git' --exclude 'venv' --exclude '__pycache__' --exclude '.env' \
        "$BASE_DIR/" "root@$SERVER_IP:/opt/WocomRobot/"
    ssh -o ConnectTimeout=8 -o StrictHostKeyChecking=no "root@$SERVER_IP" \
        "systemctl restart wocom-robot && systemctl status wocom-robot --no-pager"
    echo "🎉 云服务器更新完成并已成功生效！"
else
    echo "ℹ️  提示: 未在 .env 中设置 SERVER_IP。"
fi
echo "========================================================"
