#!/usr/bin/env python3
"""
巨量引擎 - 每日消耗报表下载 + 写飞书bitable + 发群通知
基于验证过的 ocean_downloader.py，重建完整流程
"""
import os, sys, json, time, subprocess
from datetime import date, timedelta
from playwright.sync_api import sync_playwright

# ===== 账密 =====
EMAIL = "17670937@qq.com"
PASSWORD = "HUJIA@hujia100200"

# ===== 路径 =====
OUTPUT_DIR = "/Users/test/Downloads/ocean_downloads"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===== 日期范围（无参数=本月1日~昨天） =====
if len(sys.argv) >= 3:
    START_DATE = sys.argv[1]
    END_DATE   = sys.argv[2]
else:
    yesterday = date.today() - timedelta(days=1)
    START_DATE = date(yesterday.year, yesterday.month, 1).strftime('%Y-%m-%d')
    END_DATE   = yesterday.strftime('%Y-%m-%d')

# ===== API =====
TASK_LIST_URL = "https://agent.oceanengine.com/agent/download-center/task-list"
DOWNLOAD_URL  = "https://agent.oceanengine.com/agent/download-center/download"

METRICS = ['客户', '本地推线索消耗', '本地推交易消耗', '投放形式']

# ===== 步骤1：登录 =====
def login(page):
    page.goto("https://agent.oceanengine.com/admin/fundModule/flowQuery/cost",
              wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    page.locator('input[placeholder="请输入邮箱"]').fill(EMAIL)
    page.locator('input[type="password"]').fill(PASSWORD)
    page.locator(".check-box-icon").click()
    page.locator("button:has-text('登录')").click()
    page.wait_for_timeout(8000)
    # 等待登录后 URL 跳转到目标页
    page.wait_for_url("**/flowQuery/cost**", timeout=30000)
    page.wait_for_timeout(3000)
    print("✅ 登录成功")

# ===== 步骤2：导航+设置 =====
def nav_and_setup(page):
    # 左侧菜单：商务
    page.locator('text=商务').first.click()
    page.wait_for_timeout(2000)
    page.locator('.thirdMenu-CEGpZ1').first.click()
    page.wait_for_timeout(3000)

    # 设置分日
    page.locator('text=汇总粒度').first.click()
    page.wait_for_timeout(600)
    page.locator('text=分日').first.click()
    page.wait_for_timeout(1500)

    # 设置日期范围
    page.locator('text=日期范围').first.click()
    page.wait_for_timeout(1500)
    # 用 JS 直接设 input 值
    page.evaluate(f"""
const inputs = document.querySelectorAll('input.byted-input');
for (let i = 0; i < inputs.length; i++) {{
    const v = inputs[i].value;
    if (v.includes('~') || v.includes('2026')) {{
        const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        ns.call(inputs[i], '{START_DATE} ~ {END_DATE}');
        inputs[i].dispatchEvent(new Event('input', {{ bubbles: true }}));
        inputs[i].dispatchEvent(new Event('change', {{ bubbles: true }}));
        break;
    }}
}}
""")
    page.keyboard.press('Enter')
    page.wait_for_timeout(3000)
    print(f"✅ 日期范围已设置：{START_DATE} ~ {END_DATE}")

# ===== 步骤3：选指标+导出 =====
def export_and_download(page):
    # 打开列选择器（工具栏第二个按钮）
    page.locator('button.byted-btn').nth(1).click(force=True)
    page.wait_for_timeout(2000)

    # 取消全选，再选需要的4个指标
    page.locator('.byted-checkbox:has-text("全部列")').first.click()
    page.wait_for_timeout(300)
    for m in METRICS:
        page.locator(f'.byted-checkbox:has-text("{m}")').first.click(force=True)
        page.wait_for_timeout(200)

    # 点导出（在模态框底部）
    page.locator('.byted-modal-footer button:has-text("导出")').first.click()
    page.wait_for_timeout(3000)
    print("✅ 已提交到下载中心")

# ===== 步骤4：轮询等待文件就绪 =====
def wait_for_task(page, max_wait=120):
    params = {
        "endDate": date.today().strftime('%Y-%m-%d'),
        "startDate": START_DATE,
        "page": 1, "pageSize": 5, "size": 5
    }
    for i in range(max_wait // 5):
        time.sleep(5)
        try:
            resp = page.request.get(TASK_LIST_URL, params=params)
            tasks = resp.json().get('data', {}).get('data', [])
            if tasks and tasks[0].get('taskStatus') == 'SUCCESS':
                print(f"✅ 文件就绪: {tasks[0]['fileName']}")
                return tasks[0]
            status = tasks[0].get('taskStatus', 'UNKNOWN') if tasks else '无任务'
            print(f"  [{i*5}s] 状态: {status}")
        except Exception as e:
            print(f"  [{i*5}s] 查询出错: {e}")
    return None

# ===== 步骤5：下载文件（API直接拿二进制） =====
def download_file(page, task):
    resp = page.request.get(f"{DOWNLOAD_URL}?id={task['id']}")
    content = resp.body()
    out = os.path.join(OUTPUT_DIR, task['fileName'])
    with open(out, 'wb') as f:
        f.write(content)
    return out

# ===== 主流程 =====
def run():
    print(f"日期范围: {START_DATE} ~ {END_DATE}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_context().new_page()
        try:
            login(page)
            nav_and_setup(page)
            export_and_download(page)
            task = wait_for_task(page)
            if not task:
                print("⚠️ 超时，尝试获取最新任务…")
                task = wait_for_task(page, max_wait=20)
            if task:
                out = download_file(page, task)
                print(f"🎉 下载完成: {out} ({os.path.getsize(out)} bytes)")
                return out
            else:
                print("❌ 未找到可下载文件")
                return None
        finally:
            browser.close()

if __name__ == "__main__":
    result = run()
    if not result:
        sys.exit(1)

    # 下载成功后，调用写表脚本
    print("\n调用消耗报表写表.py …")
    r = subprocess.run(
        [sys.executable, "/tmp/消耗报表写表.py"],
        capture_output=True, text=True, timeout=120
    )
    print(r.stdout)
    if r.stderr:
        print("STDERR:", r.stderr[:500])
    sys.exit(0 if r.returncode == 0 else 1)
