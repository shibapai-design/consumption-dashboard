#!/usr/bin/env python3
"""
本地推商户监控 — 重建 Dashboard HTML（嵌入最新数据）
cron 每30分钟运行一次，更新嵌入数据的 HTML
"""
import sys, json, subprocess
from datetime import datetime

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

def main():
    print(f"采集商户数据... {datetime.now().strftime('%H:%M:%S')}")
    
    results = {}
    for i, name in enumerate(MERCHANTS):
        print(f"[{i+1}/{len(MERCHANTS)}] {name}...", end=" ", flush=True)
        r = subprocess.run(
            [sys.executable, "/tmp/merchant_collect.py", name],
            capture_output=True, text=True, timeout=90
        )
        if r.returncode == 0 and r.stdout.strip():
            try:
                data = json.loads(r.stdout.strip())
                results[name] = data
                print(f"✅ {data.get('可用余额')} / {data.get('实时消耗')}")
            except:
                print(f"⚠️ 解析失败")
        else:
            print(f"❌ {r.stderr[:50] if r.stderr else '超时'}")
        if i < len(MERCHANTS) - 1:
            import time; time.sleep(2)
    
    print(f"\n采集完成: {len(results)}/{len(MERCHANTS)}")
    
    # 生成嵌入数据的 HTML
    merchants_json = json.dumps([{"name": k, **v} for k, v in results.items()], ensure_ascii=False)
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
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
.auto-refresh{{font-size:11px;color:#475569;display:flex;align-items:center;gap:6px}}
.progress-bar{{width:60px;height:4px;background:#1e293b;border-radius:2px;overflow:hidden}}
.progress-bar .fill{{height:100%;background:#3b82f6;transition:width 1s linear}}
.modal-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:100;justify-content:center;align-items:center;padding:20px}}
.modal-overlay.show{{display:flex}}
.modal{{background:#1a1d27;border:1px solid #2d3748;border-radius:12px;width:100%;max-width:480px;overflow:hidden}}
.modal-header{{padding:16px 20px;border-bottom:1px solid #2d3748;display:flex;justify-content:space-between;align-items:center}}
.modal-header h2{{font-size:16px;color:#f8fafc}}
.modal-close{{background:none;border:none;color:#64748b;font-size:20px;cursor:pointer;line-height:1;padding:4px 8px}}
.modal-close:hover{{color:#e2e8f0}}
.modal-body{{padding:20px;display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.metric-card{{background:#111318;border:1px solid #2d3748;border-radius:8px;padding:12px}}
.metric-card .label{{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px}}
.metric-card .value{{font-size:20px;font-weight:600;color:#f8fafc;margin-top:4px}}
.metric-card .sub{{font-size:11px;color:#475569;margin-top:2px}}
.footer{{text-align:center;padding:16px;color:#334155;font-size:11px}}
</style>
</head>
<body>

<div class="header">
  <h1>📊 本地推商户监控</h1>
  <div class="header-right">
    <div class="auto-refresh">
      <div class="progress-bar"><div class="fill" id="progressFill" style="width:100%"></div></div>
      <span id="countdown">30:00</span> 后自动刷新
    </div>
    <span id="updateTime">更新: {update_time}</span>
    <span class="status-dot"></span>
    <span id="merchantCount">—</span>
    <button class="refresh-btn" onclick="location.reload()">🔄 刷新</button>
  </div>
</div>

<div class="filters">
  <button class="filter-btn active" data-filter="all" onclick="setFilter('all')">全部 (13)</button>
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
        <th>商户</th><th>可用余额</th><th>实时消耗</th><th>短视频</th><th>直播</th><th>转化数</th><th>转化成本</th><th>更新时间</th><th>状态</th>
      </tr>
    </thead>
    <tbody id="tableBody"></tbody>
  </table>
</div>

<div class="modal-overlay" id="detailModal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-header">
      <h2 id="modalTitle">—</h2>
      <button class="modal-close" onclick="closeModal()">×</button>
    </div>
    <div class="modal-body" id="modalBody"></div>
  </div>
</div>

<div class="footer">
  数据来源：巨量引擎代理商后台 · 每30分钟自动更新 · 报警功能预留（暂未启用）
</div>

<script>
const DATA = {merchants_json};
const UPDATE_TIME = "{update_time}";
const allData = DATA.map(f=>({{name:f.name||"—",balance:f.可用余额||0,totalConsume:f.实时消耗||0,shortVideo:f.消耗_短视频||0,live:f.消耗_直播||0,convert:f.转化数||0,costPer:f.转化成本||0,updateTime:f.更新时间||"—"}}));
let currentFilter="all",searchText="";
const REFRESH_INTERVAL=30*60;
let countdownTimer=null,refreshTimer=null;

function formatMoney(v){{if(v>=10000)return"¥"+(v/10000).toFixed(1)+"万";if(v>=1000)return"¥"+v.toFixed(0);return"¥"+v.toFixed(2)}}
function getBalanceClass(v){{if(v<=0)return"alert";if(v<100)return"warn";return"ok"}}
function getBadgeClass(v){{if(v<=0)return"badge-alert";if(v<100)return"badge-warn";return"badge-ok"}}
function getBadgeText(v){{if(v<=0)return"⚠️ 余额耗尽";if(v<100)return"⚠️ 余额不足";return"● 正常"}}

function setFilter(f){{currentFilter=f;document.querySelectorAll(".filter-btn").forEach(b=>b.classList.remove("active"));document.querySelector(`[data-filter="${{f}}"]`).classList.add("active");render()}}
function doSearch(){{searchText=document.getElementById("searchInput").value.trim().toLowerCase();render()}}

function getFiltered(){{return allData.filter(item=>{{if(currentFilter==="warn"&&item.balance>=100)return false;if(currentFilter==="high"&&item.totalConsume<200)return false;if(searchText&&!item.name.toLowerCase().includes(searchText))return false;return true}}))}}

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
  if(data.length===0){{tbody.innerHTML='<tr><td colspan="9" class="no-data">无匹配数据</td></tr>';return}}
  tbody.innerHTML=data.map(item=>`${{`<tr onclick="showDetail('${{item.name}}')" style="cursor:pointer">
    <td class="merchant-name">${{item.name}}</td>
    <td class="balance ${{getBalanceClass(item.balance)}}">${{formatMoney(item.balance)}}</td>
    <td class="consume">${{formatMoney(item.totalConsume)}}</td>
    <td>${{item.shortVideo>0?formatMoney(item.shortVideo):'—'}}</td>
    <td>${{item.live>0?formatMoney(item.live):'—'}}</td>
    <td>${{item.convert>0?item.convert:'—'}}</td>
    <td>${{item.costPer>0?'¥'+item.costPer.toFixed(1):'—'}}</td>
    <td style="color:#475569;font-size:12px">${{item.updateTime}}</td>
    <td><span class="badge ${{getBadgeClass(item.balance)}}">${{getBadgeText(item.balance)}}</span></td>
  </tr>`)}}).join("");
}}

function showDetail(name){{
  const item=allData.find(i=>i.name===name);
  if(!item)return;
  document.getElementById("modalTitle").textContent=item.name;
  document.getElementById("modalBody").innerHTML=`
    <div class="metric-card"><div class="label">可用余额</div><div class="value" style="color:${{item.balance<100?'#f59e0b':'#10b981'}}">${{formatMoney(item.balance)}}</div></div>
    <div class="metric-card"><div class="label">实时消耗</div><div class="value">${{formatMoney(item.totalConsume)}}</div><div class="sub">${{item.updateTime}}</div></div>
    <div class="metric-card"><div class="label">短视频消耗</div><div class="value">${{item.shortVideo>0?formatMoney(item.shortVideo):'—'}}</div></div>
    <div class="metric-card"><div class="label">直播消耗</div><div class="value">${{item.live>0?formatMoney(item.live):'—'}}</div></div>
    <div class="metric-card"><div class="label">转化数</div><div class="value">${{item.convert>0?item.convert:0}}</div></div>
    <div class="metric-card"><div class="label">转化成本</div><div class="value">${{item.costPer>0?'¥'+item.costPer.toFixed(1):'—'}}</div></div>
  `;
  document.getElementById("detailModal").classList.add("show");
}}
function closeModal(){{document.getElementById("detailModal").classList.remove("show")}}

function resetTimers(){{
  clearInterval(countdownTimer);clearTimeout(refreshTimer);
  let remaining=REFRESH_INTERVAL;
  countdownTimer=setInterval(()=>{{remaining-=1;const m=Math.floor(remaining/60),s=remaining%60;document.getElementById("countdown").textContent=`${{m}}:${{s.toString().padStart(2,"0")}}`;document.getElementById("progressFill").style.width=(remaining/REFRESH_INTERVAL*100)+"%";if(remaining<=0)clearInterval(countdownTimer)}},1000);
  refreshTimer=setTimeout(()=>{{location.reload()}},REFRESH_INTERVAL*1000);
}}

render();resetTimers();
</script>
</body>
</html>'''
    
    with open("/tmp/merchant_monitor_dashboard.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"HTML已生成: /tmp/merchant_monitor_dashboard.html")
    return len(results)

if __name__ == "__main__":
    count = main()
    print(f"\n{'='*50}")
    print(f"下一步: 上传到 GitHub → Cloudflare Pages 自动部署")
