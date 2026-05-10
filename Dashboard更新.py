#!/usr/bin/env python3
"""
Dashboard更新.py — 读取Excel生成Dashboard并推送到GitHub (通过 API)
用法: python3 Dashboard更新.py --file <Excel路径>
Token 从环境变量 GITHUB_TOKEN 读取（不写在文件里）
"""
import argparse, os, sys, shutil, tempfile, datetime, urllib.request, json, ssl, subprocess, base64

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_OWNER   = "shibapai-design"
REPO_NAME    = "consumption-dashboard"
BRANCH       = "main"
COMMIT_MSG   = f"📊 更新消耗报表 dashboard ({datetime.date.today().isoformat()})"

def github_api(method, url, data=None, token=""):
    ctx = ssl.create_default_context()
    body = json.dumps(data).encode() if data else None
    headers = {
        "Authorization": f"token {token or GITHUB_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github.v3+json"
    }
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        return json.loads(resp.read())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()

    excel_path = args.file
    if not os.path.exists(excel_path):
        print(f"Excel 文件不存在: {excel_path}")
        sys.exit(1)

    token = GITHUB_TOKEN
    if not token:
        print("ERROR: 需要设置环境变量 GITHUB_TOKEN")
        sys.exit(1)

    # 1. 生成 dashboard.html
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dashboard_gen = os.path.join(script_dir, "Dashboard生成.py")
    if not os.path.exists(dashboard_gen):
        print(f"Dashboard生成.py 不存在: {dashboard_gen}")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_html = os.path.join(tmpdir, "dashboard.html")
        r = subprocess.run(
            [sys.executable, dashboard_gen, "--file", excel_path, "--output", output_html],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode != 0:
            print("Dashboard生成失败:", r.stderr[:300])
            sys.exit(1)
        print("Dashboard生成成功")

        with open(output_html, "r", encoding="utf-8") as f:
            html_content = f.read()

    # 2. 获取当前 SHA
    sha = None
    try:
        existing = github_api(
            "GET",
            f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/dashboard.html?ref={BRANCH}",
            token=token
        )
        sha = existing.get("sha")
        print(f"当前文件 SHA: {sha[:8]}...")
    except Exception as e:
        print(f"文件不存在，将创建新文件 ({e})")

    # 3. 通过 API 上传/更新
    update_data = {
        "message": COMMIT_MSG,
        "content": base64.b64encode(html_content.encode("utf-8")).decode("ascii"),
        "branch": BRANCH
    }
    if sha:
        update_data["sha"] = sha

    result = github_api(
        "PUT",
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/dashboard.html",
        data=update_data,
        token=token
    )
    commit = result.get("commit", {})
    sha_new = commit.get("sha", "")[:8]
    print(f"✅ 已提交 SHA: {sha_new}")
    print(f"   GitHub Actions 触发 Cloudflare Pages 部署中...")
    print(f"   预计 1-2 分钟生效: https://consumption-dashboard.pages.dev")


if __name__ == "__main__":
    main()
