#!/usr/bin/env bash
# ==============================================================================
# setup_cron.sh — 在服务器上一键完成 BaiduPCS-Py 安装 + cron 配置
# 用法（在服务器上执行）：
#   bash /opt/WocomRobot/sync/setup_cron.sh
#
# 执行完毕后需要手动完成一次性登录（见脚本末尾提示）。
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SYNC_SCRIPT="$SCRIPT_DIR/pan_sync.py"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/pan_sync.log"
PYTHON_BIN="$(which python3)"

echo "============================================================"
echo "🔧 Step 1: 安装 BaiduPCS-Py 与 python-dotenv"
echo "============================================================"
pip3 install --quiet BaiduPCS-Py python-dotenv
echo "✅ 依赖安装完成"

echo ""
echo "============================================================"
echo "📁 Step 2: 创建日志目录"
echo "============================================================"
mkdir -p "$LOG_DIR"
echo "✅ 日志目录: $LOG_FILE"

echo ""
echo "============================================================"
echo "⏰ Step 3: 配置 cron 增量同步（每天 08:00 和 20:00 各执行一次）"
echo "============================================================"

CRON_JOB="0 8,20 * * * cd $PROJECT_DIR && $PYTHON_BIN $SYNC_SCRIPT >> $LOG_FILE 2>&1"

# 检查是否已存在相同的 cron 任务，避免重复添加
if crontab -l 2>/dev/null | grep -qF "$SYNC_SCRIPT"; then
    echo "ℹ️  cron 任务已存在，跳过添加。当前任务："
    crontab -l | grep "$SYNC_SCRIPT"
else
    # 追加到现有 crontab
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "✅ cron 任务已添加：$CRON_JOB"
fi

echo ""
echo "============================================================"
echo "🔑 Step 4: 验证 BaiduPCS-Py 安装"
echo "============================================================"
BaiduPCS-Py version || true

echo ""
echo "============================================================"
echo "✅ 安装完成！接下来需要完成一次性百度网盘登录："
echo ""
echo "  方式 A（推荐 — Cookie 登录，无需手机验证）："
echo "    BaiduPCS-Py useradd"
echo "    # 按提示输入 BDUSS 和 STOKEN（从浏览器 F12 → Application → Cookies 复制）"
echo ""
echo "  方式 B（环境变量，每次运行临时使用）："
echo "    在 $PROJECT_DIR/.env 中添加："
echo "      BAIDU_BDUSS=你的BDUSS值"
echo "      BAIDU_STOKEN=你的STOKEN值"
echo "      BAIDU_PAN_ROOT_DIR=/相册交付        # 修改为你的实际目录"
echo "      BAIDU_SHARE_PWD=                   # 留空=随机4位，或填固定密码"
echo ""
echo "  登录完成后，手动验证一次同步效果："
echo "    cd $PROJECT_DIR"
echo "    SYNC_DRY_RUN=1 python3 sync/pan_sync.py   # 只预览，不写入"
echo "    python3 sync/pan_sync.py                   # 正式写入"
echo ""
echo "  查看日志："
echo "    tail -f $LOG_FILE"
echo "============================================================"
