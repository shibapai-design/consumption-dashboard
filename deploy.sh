#!/bin/bash
# deploy.sh — GitHub Actions 调用此脚本部署 dashboard 到 Cloudflare Pages
# 环境变量: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID

set -e

echo "=== 部署到 Cloudflare Pages ==="
echo "Account ID: ${CLOUDFLARE_ACCOUNT_ID:0:8}..."
echo "仓库: $(git remote get-url origin)"

# 安装 Wrangler (Cloudflare CLI)
npm install -g wrangler 2>/dev/null || true
wrangler auth --token "$CLOUDFLARE_API_TOKEN" 2>/dev/null || true

# 部署 (不询问，直接部署当前目录)
echo "开始部署..."
OUTPUT=$(wrangler pages deploy . --project-name=consumption-dashboard --commit-hash="$GITHUB_SHA" 2>&1) || true
echo "$OUTPUT"

# 提取部署后的 URL
DEPLOY_URL=$(echo "$OUTPUT" | grep -o 'https://[^ ]*\.pages\.dev' | head -1)
if [ -n "$DEPLOY_URL" ]; then
  echo "DEPLOY_URL=$DEPLOY_URL" >> "$GITHUB_ENV"
  echo "✅ 部署成功: $DEPLOY_URL"
else
  echo "⚠️ 无法从输出中提取 URL，部署可能仍成功请检查 Cloudflare Dashboard"
fi