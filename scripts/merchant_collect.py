#!/usr/bin/env python3
"""
本地推商户监控 — 单商户采集模式（避免浏览器资源泄漏）
"""
import sys, os, json, time, re
from datetime import datetime
from playwright.sync_api import sync_playwright

EMAIL = "17670937@qq.com"
PASSWORD = "HUJIA@hujia100200"

MERCHANTS = [
    "荆州森屿男士美发",
    "门博士直播",
    "门博士博恩斯",
    "门博士家居",
    "荆州跃动悦型健身",
    "荆州御松家居",
    "清雅全屋定制",
    "壹嘉装饰",
    "荆州市乐家金装",
    "鼎慕装饰_荆门公司新",
    "鼎慕装饰_沙洋分公司",
    "鼎慕装饰_钟祥公司j",
    "荆州欧艺装饰",
]

def parse_number(text):
    if not text: return 0.0
    text = text.strip().replace(",", "").replace(" ", "")
    m = re.search(r"[\d.]+", text)
    if m:
        try: return float(m.group())
        except: return 0.0
    return 0.0

def parse_int(text):
    if not text: return 0
    text = text.strip().replace(",", "")
    m = re.search(r"[\d]+", text)
    if m:
        try: return int(m.group())
        except: return 0
    return 0

def collect_merchant(merchant_name):
    """采集单个商户，返回数据或None"""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        try:
            context = browser.new_context()
            page = context.new_page()
            
            # 打开账户列表页
            page.goto(
                "https://agent.oceanengine.com/admin/companyModule/account/management/local",
                wait_until="domcontentloaded",
                timeout=30000
            )
            page.wait_for_timeout(3000)
            
            # 登录
            try:
                page.locator('input[placeholder="请输入邮箱"]').fill(EMAIL)
                page.locator('input[type="password"]').fill(PASSWORD)
                page.locator(".check-box-icon").click()
                page.locator("button:has-text('登录')").click()
                page.wait_for_timeout(8000)
                page.wait_for_url("**/local**", timeout=30000)
            except:
                pass  # 可能已登录
            
            page.wait_for_timeout(2000)
            
            # 搜索
            try:
                page.locator('input[placeholder*="本地推账户"]').first.fill(merchant_name)
                page.keyboard.press("Enter")
                page.wait_for_timeout(3000)
            except Exception as e:
                return None, f"搜索失败: {e}"
            
            # 进入
            try:
                page.locator("text=进入本地推").first.click(timeout=5000)
                page.wait_for_timeout(5000)
            except Exception as e:
                return None, f"进入本地推失败: {e}"
            
            if len(context.pages) < 2:
                return None, "未打开新标签页"
            
            new_tab = context.pages[-1]
            new_tab.wait_for_timeout(3000)
            
            # 解析
            text = new_tab.evaluate("document.body.innerText")
            lines = text.split("\n")
            
            result = {
                "可用余额": 0.0,
                "实时消耗": 0.0,
                "消耗_短视频": 0.0,
                "消耗_直播": 0.0,
                "转化数": 0,
                "转化成本": 0.0,
            }
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if "账户总余额" in line:
                    for j in range(i+1, min(i+4, len(lines))):
                        v = parse_number(lines[j])
                        if v > 0: result["可用余额"] = v; break
                elif "标准投放消耗" in line:
                    for j in range(i+1, min(i+4, len(lines))):
                        v = parse_number(lines[j])
                        if v >= 0: result["消耗_短视频"] = v; break
                elif "全域投放消耗" in line:
                    for j in range(i+1, min(i+4, len(lines))):
                        v = parse_number(lines[j])
                        if v >= 0: result["消耗_直播"] = v; break
                elif "线索留资数" in line and "计费时间" not in line:
                    for j in range(i+1, min(i+4, len(lines))):
                        v = parse_int(lines[j])
                        if v >= 0: result["转化数"] = v; break
                i += 1
            
            result["实时消耗"] = result["消耗_短视频"] + result["消耗_直播"]
            if result["转化数"] > 0 and result["实时消耗"] > 0:
                result["转化成本"] = round(result["实时消耗"] / result["转化数"], 2)
            
            new_tab.close()
            context.close()
            browser.close()
            
            return result, None
            
        except Exception as e:
            try:
                context.close()
            except: pass
            try:
                browser.close()
            except: pass
            return None, str(e)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 merchant_collect.py <商户名称>")
        sys.exit(1)
    
    name = sys.argv[1]
    result, err = collect_merchant(name)
    
    if err:
        print(f"ERROR: {err}")
        sys.exit(1)
    else:
        print(json.dumps(result, ensure_ascii=False))
