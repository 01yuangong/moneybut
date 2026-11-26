#!/usr/bin/env bash
# 一键部署到 Ubuntu 22.04 / Debian 12（1 核 1G 足够）
# 用法：sudo bash deploy/deploy.sh your-domain.com
set -euo pipefail

DOMAIN="${1:-}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP=/opt/moneybot

echo "==> 1/6 安装系统依赖"
apt-get update -qq
apt-get install -y -qq python3 nginx curl >/dev/null

echo "==> 2/6 创建用户与目录"
id -u moneybot >/dev/null 2>&1 || useradd -r -m -d "$APP" -s /usr/sbin/nologin moneybot
mkdir -p "$APP" "$APP/data" "$APP/site"
cp -r "$SRC"/core "$SRC"/main.py "$SRC"/serve.py "$SRC"/config.json "$APP"/
cp -r "$SRC"/data/fixtures "$APP"/data/
chown -R moneybot:moneybot "$APP"

echo "==> 3/6 生成密钥与域名配置"
ADMIN_TOKEN="$(head -c 24 /dev/urandom | base64 | tr -d '/+=')"
SECRET="$(head -c 24 /dev/urandom | base64 | tr -d '/+=')"
BASE="http://${DOMAIN:-$(curl -s -4 ifconfig.me)}"
sed -i "s#https://example.com#${BASE}#g" "$APP/config.json" || true

echo "==> 4/6 安装 systemd 服务"
sed -e "s#https://your-domain.com#${BASE}#g" \
    -e "s#ADMIN_TOKEN=CHANGE_ME_LONG_RANDOM#ADMIN_TOKEN=${ADMIN_TOKEN}#" \
    "$SRC/deploy/moneybot-web.service" > /etc/systemd/system/moneybot-web.service
sed -e "s#https://your-domain.com#${BASE}#g" \
    "$SRC/deploy/moneybot.service" > /etc/systemd/system/moneybot.service
cp "$SRC/deploy/moneybot.timer" /etc/systemd/system/moneybot.timer
echo "MONEYBOT_SECRET=${SECRET}" >> /etc/systemd/system/moneybot-web.service

echo "==> 5/6 先手动跑一期，确认能出内容"
sudo -u moneybot MONEYBOT_DB="$APP/data/state.db" \
  MONEYBOT_BASE_URL="$BASE" python3 "$APP/main.py" run --base-url "$BASE" || \
  echo "!! 首跑失败（可能出网被限），先看日志：journalctl -u moneybot -n 50"

if [[ -n "$DOMAIN" ]]; then
  sed "s#your-domain.com#${DOMAIN}#g" "$SRC/deploy/nginx.conf" > /etc/nginx/sites-available/moneybot
  ln -sf /etc/nginx/sites-available/moneybot /etc/nginx/sites-enabled/moneybot
  rm -f /etc/nginx/sites-enabled/default
  nginx -t && systemctl reload nginx
fi

echo "==> 6/6 启动"
systemctl daemon-reload
systemctl enable --now moneybot-web.service
systemctl enable --now moneybot.timer
systemctl list-timers moneybot.timer --no-pager || true

echo
echo "完成。"
echo "  站点      : $BASE"
echo "  后台统计  : curl -H 'X-Admin-Token: ${ADMIN_TOKEN}' $BASE/api/stats"
echo "  定时任务  : systemctl list-timers | grep moneybot"
echo "  HTTPS     : apt install -y certbot python3-certbot-nginx && certbot --nginx -d $DOMAIN"
