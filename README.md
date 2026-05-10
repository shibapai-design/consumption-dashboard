# 消耗报表 Dashboard

飞书群收到 Excel 文件后自动生成可视化 Dashboard，托管在 Cloudflare Pages。

## 数据流程

```
飞书群发 Excel → 莱昂拉多德彪机器人 → Dashboard更新.py
                                              ↓
                                       GitHub (push)
                                              ↓
                                    GitHub Actions 触发
                                              ↓
                                    Cloudflare Pages 部署
                                              ↓
                                    📊 新网址自动生效
```

## Cloudflare 配置（首次需要）

1. 注册 Cloudflare: https://dash.cloudflare.com
2. 获取 **Account ID**: Cloudflare Dashboard → 右上角个人头像 → 右侧面板 → Account ID
3. 创建 **API Token**: Cloudflare Dashboard → Profile → API Tokens → Create Token
   - 使用 "Custom token" → 开始配置
   - Account Permissions: `Cloudflare Pages: Edit`
   - Account: 选你的账号
   - 创建后复制 token
4. 在 GitHub 仓库 Settings → Secrets 添加:
   - `CLOUDFLARE_API_TOKEN` = 你的 API Token
   - `CLOUDFLARE_ACCOUNT_ID` = 你的 Account ID

## 部署网址

- 主站: https://consumption-dashboard.pages.dev
- 备用: https://shibapai-design.github.io/consumption-dashboard

## 文件说明

- `Dashboard生成.py` — 读取 Excel 生成 HTML Dashboard
- `Dashboard更新.py` — 本地更新脚本（飞书机器人调用此脚本）
- `deploy.sh` — GitHub Actions 调用（自动部署到 Cloudflare Pages）
- `dashboard.html` — 当前生效的 Dashboard 页面