#!/usr/bin/env python3
"""
本地推商户实时数据监控 — 从本地推后台抓取13个账户的实时数据，写入飞书多维表格
每30分钟自动运行，覆盖当日数据
"""
import os, sys, json, time, glob, concurrent.futures
from datetime import date, datetime, timedelta
from playwright.sync_api import sync_playwright
import requests

# ===== 配置 =====
EMAIL = "17670937@qq.com"
PASSWORD = "HUJIA@hujia100200"

FEISHU_APP_ID = "cli_a976b9b729fa9bb3"
FEISHU_APP_SECRET = "k0lyGolc88vm59YTHkBohcHmTJjcA5Ub"
FEISHU_APP_TOKEN = "W6apbYhDjaQjDbs83K8cWb1hnce"
FEISHU_TABLE_ID = "tblgcjlG9IQEt8iT"

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

# ===== 工具函数 =====
def get_feishu_token():
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10
    )
    return r.json()["tenant_access_token"]

def get_record_id_map(token):
    r = requests.get(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{FEISHU_APP_TOKEN}/tables/{FEISHU_TABLE_ID}/records",
        headers={"Authorization": f"Bearer {token}"},
        params={"page_size": 100}, timeout=10
    )
    name_map = {}
    for rec in r.json()["data"]["items"]:
        name = rec["fields"].get("商户名称", "")
        if name:
            name_map[name] = rec["record_id"]
    return name_map

def update_one_record(token, record_id, fields):
    resp = requests.put(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{FEISHU_APP_TOKEN}/tables/{FEISHU_TABLE_ID}/records/{record_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"fields": fields}, timeout=15
    )
    return resp.json().get("code") == 0

# ===== 抓取单个账户数据 =====
def fetch_merchant_data(page, merchant):
    """在当前页操作：搜索账户→进入本地推→抓数据→返回"""
    try:
        # 搜索
        page.locator('input[placeholder*="本地推账户"]').first.fill(merchant)
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)
        
        # 点进入本地推
        page.locator("text=进入本地推").first.click(timeout=5000)
        page.wait_for_timeout(5000)
        
        new_tab = page.context.pages[-1]
        new_tab.evaluate("""() => { document.querySelectorAll('[class*="modal"]').forEach(el => el.remove()); }""")
        new_tab.wait_for_timeout(1000)
        
        # 提取数据
        data = new_tab.evaluate("""
() => {
    const metrics = {};
    const cards = document.querySelectorAll('[class*="metric-card"], [class*="promotion-metric"]');
    for (const c of cards) {
        const text = (c.innerText || '').trim().replace(/\\s+/g, ' ');
        const nums = text.match(/[\\d,.]+/g);
        const labels = text.split(/[\\d,.]+/);
        if (nums && nums.length > 0 && labels.length > 1) {
            const label = labels[0].trim().replace(/\\s+/g, '');
            if (label) metrics[label] = nums[0];
        }
    }
    const balanceEl = document.querySelector('[class*="balance"]');
    const balance = balanceEl ? (balanceEl.innerText || '').match(/[\\d,.]+/g) : [];
    return {
        metrics,
        balance: balance[0] || '',
    };
}
        """)
        
        new_tab.close()
        
        # 清空搜索框（回到列表）
        page.locator('input[placeholder*="本地推账户"]').first.fill("")
        page.wait_for_timeout(500)
        
        return merchant, data, None
        
    except Exception as e:
        return merchant, None, str(e)

# ===== 主流程 =====
def run():
    now_ts = int(datetime.now().timestamp() * 1000)
    today_str = "2026-05-11"
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始抓取本地推数据...")
    
    # 启动浏览器
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        page = context.new_page()
        
        # 登录
        page.goto(
            "https://agent.oceanengine.com/admin/companyModule/account/management/local",
            wait_until="domcontentloaded", timeout=30000
        )
        page.wait_for_timeout(2000)
        page.locator('input[placeholder="请输入邮箱"]').fill(EMAIL)
        page.locator('input[type="password"]').fill(PASSWORD)
        page.locator(".check-box-icon").click()
        page.locator("button:has-text('登录')").click()
        page.wait_for_timeout(8000)
        print("  ✅ 登录成功")
        
        # 抓取所有账户
        merchant_results = {}
        for merchant in MERCHANTS:
            name, data, err = fetch_merchant_data(page, merchant)
            if err:
                print(f"  ⚠️ {name}: {err}")
                merchant_results[name] = None
            else:
                merchant_results[name] = data
        
        context.close()
        browser.close()
    
    # 保存原始数据
    with open('/tmp/merchant_data.json', 'w') as f:
        json.dump(merchant_results, f, ensure_ascii=False, indent=2)
    
    # 写入飞书
    print("  写入飞书多维表格...")
    token = get_feishu_token()
    name_map = get_record_id_map(token)
    
    def build_and_update(merchant):
        data = merchant_results.get(merchant)
        if not data:
            return f"⚠️ 无数据: {merchant}"
        
        metrics = data.get("metrics", {})
        consume_str = metrics.get("消耗(元)", "0").replace(",", "")
        consume = float(consume_str) if consume_str else 0
        
        conv_str = metrics.get("线索留资数(计费时间)", "0").replace(",", "")
        conv = int(float(conv_str)) if conv_str else 0
        
        conv_cost = round(consume / conv, 2) if conv > 0 else 0
        
        balance_str = (data.get("balance") or "0").replace(",", "")
        balance = float(balance_str) if balance_str else 0
        
        record_id = name_map.get(merchant)
        if not record_id:
            return f"⚠️ 未找到记录: {merchant}"
        
        fields = {
            "实时消耗": consume,
            "转化数": conv,
            "转化成本": conv_cost,
            "可用余额": balance,
            "消耗_短视频": 0,
            "消耗_直播": 0,
            "更新时间": now_ts,
        }
        
        ok = update_one_record(token, record_id, fields)
        return f"{'✅' if ok else '❌'} {merchant}: 消耗={consume}, 转化={conv}"
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(build_and_update, MERCHANTS))
    
    for r in results:
        print(f"  {r}")
    
    success = sum(1 for r in results if r.startswith("✅"))
    print(f"\n完成：{success}/{len(MERCHANTS)} 条更新成功")
    
    # ── 重建 Dashboard 并推送 GitHub ─────────────────────────
    print("\n🔄 重建 Dashboard HTML...")
    try:
        import base64, urllib.request, urllib.error
        
        # 读取保存的原始数据
        with open('/tmp/merchant_data.json', 'r') as f:
            raw = json.load(f)
        
        # 转换为 dashboard 需要的格式
        def parse_num(v):
            if not v: return 0
            if isinstance(v, (int, float)): return v
            try: return float(str(v).replace(',', ''))
            except: return 0
        
        merchants_data = {}
        for name, rec in raw.items():
            if not rec:
                continue
            m = rec.get('metrics', {})
            balance = parse_num(rec.get('balance'))
            consume = parse_num(m.get('消耗(元)', 0))
            conv = int(parse_num(m.get('线索留资数(计费时间)', 0)))
            conv_cost = round(consume / conv, 2) if conv > 0 else 0
            merchants_data[name] = {
                '可用余额': balance,
                '实时消耗': consume,
                '消耗_短视频': 0,   # 后台首页无此粒度
                '消耗_直播': 0,
                '转化数': conv,
                '转化成本': conv_cost,
                '更新时间': datetime.now().strftime('%Y-%m-%d %H:%M'),
            }
        
        update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        merchants_json = json.dumps([{"name": k, **v} for k, v in merchants_data.items()], ensure_ascii=False)
        
        # 生成 HTML（内嵌数据，无短视频/直播拆分列）
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>本地推商户监控</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh}}
.header{{background:linear-gradient(135deg,#1a1d27 0%,#111318 100%);border-bottom:1px solid #2d3748;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}}
.header h1{{font-size:20px;font-weight:600;color:#f8fafc;display:flex;align-items:center;gap:8px}}
.header-right{{display:flex;align-items:center;gap:16px;font-size:13px;color:#94a3b8}}
.status-dot{{width:8px;height:8px;border-radius:50%;background:#10b981;display:inline-block;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.4}}}}
.refresh-btn{{background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px;transition:all 0.2s}}
.refresh-btn:hover{{background:#334155}}
.filters{{padding:12px 24px;background:#1a1d27;border-bottom:1px solid #1e293b;display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
.filter-btn{{background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:5px 12px;border-radius:20px;cursor:pointer;font-size:12px;transition:all 0.2s}}
.filter-btn:hover,.filter-btn.active{{background:#3b82f6;border-color:#3b82f6;color:#fff}}
.search-box{{background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:5px 12px;border-radius:6px;font-size:12px;width:140px;outline:none}}
.search-box:focus{{border-color:#3b82f6}}
.summary-bar{{padding:12px 24px;background:#1e293b;display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;border-bottom:1px solid #2d3748}}
.summary-item{{text-align:center}}
.summary-item .label{{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px}}
.summary-item .value{{font-size:18px;font-weight:600;color:#f8fafc;margin-top:2px}}
.table-container{{padding:16px 24px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
thead th{{background:#1a1d27;color:#64748b;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;padding:10px 12px;text-align:left;border-bottom:1px solid #2d3748;white-space:nowrap;position:sticky;top:0}}
tbody tr{{border-bottom:1px solid #1e293b;transition:background 0.15s}}
tbody tr:hover{{background:#1a1d27}}
tbody td{{padding:10px 12px;color:#cbd5e1;white-space:nowrap}}
.merchant-name{{font-weight:500;color:#f1f5f9;max-width:160px;overflow:hidden;text-overflow:ellipsis}}
.balance{{font-weight:600}}
.balance.ok{{color:#10b981}}
.balance.warn{{color:#f59e0b}}
.balance.alert{{color:#ef4444}}
.consume{{color:#60a5fa;font-weight:500}}
.badge{{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500}}
.badge-ok{{background:#064e3b;color:#10b981}}
.badge-warn{{background:#78350f;color:#f59e0b}}
.badge-alert{{background:#7f1d1d;color:#ef4444}}
.no-data,.loading{{text-align:center;padding:60px;color:#475569;font-size:14px}}
.footer{{text-align:center;padding:16px;color:#334155;font-size:11px}}
</style>
</head>
<body>
<div class="header">
  <h1>📊 本地推商户监控</h1>
  <div class="header-right">
    <span id="updateTime">更新: {update_time}</span>
    <span class="status-dot"></span>
    <span id="merchantCount">—</span>
    <button class="refresh-btn" onclick="location.reload()">🔄 刷新</button>
  </div>
</div>
<div class="filters">
  <button class="filter-btn active" data-filter="all" onclick="setFilter('all')">全部</button>
  <button class="filter-btn" data-filter="warn" onclick="setFilter('warn')">⚠️ 余额不足</button>
  <button class="filter-btn" data-filter="high" onclick="setFilter('high')">🔥 高消耗</button>
  <input type="text" class="search-box" placeholder="🔍 搜索商户..." id="searchInput" oninput="doSearch()">
</div>
<div class="summary-bar" id="summaryBar">
  <div class="summary-item"><div class="label">商户总数</div><div class="value" id="totalMerchants">—</div></div>
  <div class="summary-item"><div class="label">账户总余额</div><div class="value" id="totalBalance">—</div></div>
  <div class="summary-item"><div class="label">今日总消耗</div><div class="value" id="totalConsume">—</div></div>
  <div class="summary-item"><div class="label">总转化数</div><div class="value" id="totalConvert">—</div></div>
  <div class="summary-item"><div class="label">平均转化成本</div><div class="value" id="avgCost">—</div></div>
</div>
<div class="table-container" id="tableContainer">
  <div class="loading" id="loadingState">加载中...</div>
  <table id="dataTable" style="display:none">
    <thead>
      <tr>
        <th>商户</th><th>可用余额</th><th>实时消耗</th><th>转化数</th><th>转化成本</th><th>更新时间</th><th>状态</th>
      </tr>
    </thead>
    <tbody id="tableBody"></tbody>
  </table>
</div>
<div class="footer">
  数据来源：巨量引擎代理商后台 · 每30分钟自动更新
</div>
<script>
const DATA = {merchants_json};
const UPDATE_TIME = "{update_time}";
const allData = DATA.map(f=>({{name:f.name||"—",balance:f.可用余额||0,totalConsume:f.实时消耗||0,convert:f.转化数||0,costPer:f.转化成本||0,updateTime:f.更新时间||"—"}}));
let currentFilter="all",searchText="";

function formatMoney(v){{if(v>=10000)return"¥"+(v/10000).toFixed(1)+"万";if(v>=1000)return"¥"+v.toFixed(0);return"¥"+v.toFixed(2)}}
function getBalanceClass(v){{if(v<=0)return"alert";if(v<100)return"warn";return"ok"}}
function getBadgeClass(v){{if(v<=0)return"badge-alert";if(v<100)return"badge-warn";return"badge-ok"}}
function getBadgeText(v){{if(v<=0)return"⚠️ 余额耗尽";if(v<100)return"⚠️ 余额不足";return"● 正常"}}

function setFilter(f){{currentFilter=f;document.querySelectorAll(".filter-btn").forEach(b=>b.classList.remove("active"));document.querySelector(`[data-filter="${{f}}"]`).classList.add("active");render()}}
function doSearch(){{searchText=document.getElementById("searchInput").value.trim().toLowerCase();render()}}

function getFiltered(){{return allData.filter(item=>{{if(currentFilter==="warn"&&item.balance>=100)return false;if(currentFilter==="high"&&item.totalConsume<200)return false;if(searchText&&!item.name.toLowerCase().includes(searchText))return false;return true}})}}

function render(){{
  const data=getFiltered();
  document.getElementById("loadingState").style.display="none";
  document.getElementById("dataTable").style.display="";
  const totalBalance=allData.reduce((s,i)=>s+(i.balance||0),0);
  const totalConsume=allData.reduce((s,i)=>s+(i.totalConsume||0),0);
  const totalConvert=allData.reduce((s,i)=>s+(i.convert||0),0);
  const avgCost=totalConvert>0?totalConsume/totalConvert:0;
  document.getElementById("totalMerchants").textContent=allData.length;
  document.getElementById("totalBalance").textContent=formatMoney(totalBalance);
  document.getElementById("totalConsume").textContent=formatMoney(totalConsume);
  document.getElementById("totalConvert").textContent=totalConvert;
  document.getElementById("avgCost").textContent=totalConvert>0?"¥"+avgCost.toFixed(1):"—";
  document.querySelector("[data-filter='warn']").textContent=`⚠️ 余额不足 (${{allData.filter(i=>i.balance<100).length}})`;
  document.querySelector("[data-filter='high']").textContent=`🔥 高消耗 (${{allData.filter(i=>i.totalConsume>=200).length}})`;
  document.getElementById("merchantCount").textContent=`${{data.length}} 商户`;
  const tbody=document.getElementById("tableBody");
  if(data.length===0){{tbody.innerHTML='<tr><td colspan="7" class="no-data">无匹配数据</td></tr>';return}}
  tbody.innerHTML=data.map(item=>'<tr>\
    <td class="merchant-name">'+(item.name||'—')+'</td>\
    <td class="balance '+getBalanceClass(item.balance)+'">'+formatMoney(item.balance)+'</td>\
    <td class="consume">'+formatMoney(item.totalConsume)+'</td>\
    <td>'+(item.convert>0?item.convert:'—')+'</td>\
    <td>'+(item.costPer>0?'¥'+item.costPer.toFixed(1):'—')+'</td>\
    <td style="color:#475569;font-size:12px">'+(item.updateTime||'—')+'</td>\
    <td><span class="badge '+getBadgeClass(item.balance)+'">'+getBadgeText(item.balance)+'</span></td>\
  </tr>').join('');
}}

render();
</script>
</body>
</html>'''
        
        # 推送 GitHub
        TOKEN = "${GH_TOKEN}"
        REPO = "shibapai-design/consumption-dashboard"
        headers = {
            "Authorization": f"token {TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
        api_url = f"https://api.github.com/repos/{REPO}/contents/monitor/index.html"
        
        get_req = urllib.request.Request(api_url, headers=headers)
        try:
            with urllib.request.urlopen(get_req) as r:
                sha = json.loads(r.read())["sha"]
        except urllib.error.HTTPError as e:
            sha = None if e.code == 404 else None
        
        payload = {
            "message": f"Update merchant monitor: {len(merchants_data)} merchants, {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": base64.b64encode(html.encode("utf-8")).decode("ascii"),
            "branch": "main",
        }
        if sha:
            payload["sha"] = sha
        
        put_req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="PUT"
        )
        with urllib.request.urlopen(put_req) as r:
            result = json.loads(r.read())
        print(f"✅ Dashboard 已推送 GitHub: {result.get('commit', {}).get('html_url', '')}")
    except Exception as e:
        print(f"⚠️ Dashboard 推送失败: {e}")
    # ── Dashboard 重建完成 ──────────────────────────────────
    
    return success == len(MERCHANTS)

if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
