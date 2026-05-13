#!/usr/bin/env python3
"""巨量引擎消耗报表 — 读取Excel并写入飞书多维表格，然后发群通知并推送Dashboard"""
import sys, os, json, time, glob, urllib.request, urllib.error
from datetime import date, datetime, timedelta
import requests

# ===== 配置 =====
APP_TOKEN = "ZV2kbuqsNaELsfs0fkMcC3NUnde"
TABLE_ID  = "tblmole67buC8zVQ"
GROUP_ID  = "oc_8f778f85cc100c6b64fec995d1be5ffc"
BOT_APP_ID     = "cli_a976b9b729fa9bb3"
BOT_APP_SECRET = "k0lyGolc88vm59YTHkBohcHmTJjcA5Ub"
BITABLE_LINK   = "https://ZV2kbuqsNaELsfs0fkMcC3NUnde.feishu.cn/wiki/tblmole67buC8zVQ"
BITABLE_MOBILE = "https://mxc4p3lj7pi.feishu.cn/base/ZV2kbuqsNaELsfs0fkMcC3NUnde?table=blkJ2YvbQ36Evq6R"
DOWNLOAD_DIR   = "/Users/test/Downloads/ocean_downloads"

# GitHub 配置
GH_TOKEN = os.environ.get("GH_TOKEN", "${GH_TOKEN}")
GH_REPO  = "shibapai-design/consumption-dashboard"
GH_HTML_PATH = "index.html"

# ===== 工具函数 =====
def get_app_token():
    r = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": BOT_APP_ID, "app_secret": BOT_APP_SECRET}, timeout=10)
    r.raise_for_status()
    return r.json()["tenant_access_token"]

def get_fields(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/fields",
        headers=headers, timeout=10)
    r.raise_for_status()
    fm = {}
    for f in r.json().get("data", {}).get("items", []):
        fm[f.get("field_name", "").strip()] = {"id": f.get("field_id", ""), "type": f.get("type", 1)}
    return fm

def ensure_field(token, name, ftype):
    headers = {"Authorization": f"Bearer {token}"}
    fm = get_fields(token)
    if name in fm:
        return fm[name]
    r = requests.post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/fields",
        headers=headers, json={"field_name": name, "type": ftype}, timeout=10)
    r.raise_for_status()
    fid = r.json()["data"]["field"]["field_id"]
    print(f"  ✓ 创建字段「{name}」({fid})")
    return {"id": fid, "type": ftype}

def find_latest_excel():
    files = glob.glob(f"{DOWNLOAD_DIR}/*.xlsx")
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def parse_date(val):
    """解析Excel日期值，返回 YYYY-MM-DD"""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, date):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    for fmt in ["%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s

def read_and_aggregate(path):
    """
    读取Excel，按 (账户名, 日期) 聚合。
    Excel真实列名：时间, 广告主账户id, 广告主账户名称, 本地线索消耗, 本地推交易消耗, 投放形式
    投放形式：'非直播计划' → 短视频，'直播计划' → 直播
    """
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    col_idx = {h: i for i, h in enumerate(headers)}

    def col(name, row):
        idx = col_idx.get(name)
        return row[idx] if idx is not None else None

    agg = {}
    for row in rows[1:]:
        account = str(col("广告主账户名称", row) or "").strip()
        date_str = parse_date(col("时间", row) or "")
        xian_suo = float(col("本地线索消耗", row) or 0)
        jiao_yi  = float(col("本地推交易消耗", row) or 0)
        form     = str(col("投放形式", row) or "").strip()

        if not account or not date_str:
            continue

        key = (account, date_str)
        if key not in agg:
            agg[key] = {
                "account": account,
                "日期": date_str,
                "线索金额": 0, "线索-短视频": 0, "线索-直播": 0,
                "交易金额": 0, "交易-短视频": 0, "交易-直播": 0,
            }

        agg[key]["线索金额"] += xian_suo
        agg[key]["交易金额"] += jiao_yi

        if form == "非直播计划":
            agg[key]["线索-短视频"] += xian_suo
            agg[key]["交易-短视频"] += jiao_yi
        elif form == "直播计划":
            agg[key]["线索-直播"] += xian_suo
            agg[key]["交易-直播"] += jiao_yi
        else:
            agg[key]["线索-短视频"] += xian_suo
            agg[key]["交易-短视频"] += jiao_yi

    records = list(agg.values())
    records.sort(key=lambda x: (x["account"], x["日期"]))
    return records

def write_records(token, records, start_date, end_date):
    """批量写入记录到bitable"""
    ensure_field(token, "总消耗", 2)
    ensure_field(token, "前一日消耗", 2)
    time.sleep(1)

    fm = get_fields(token)

    def ts(d):
        return int(datetime.strptime(d, "%Y-%m-%d").timestamp() * 1000)

    by_date = sorted(records, key=lambda x: x["日期"])
    date_totals = {}
    prev_total = 0
    for r in by_date:
        total = r["线索金额"] + r["交易金额"]
        date_totals[r["日期"]] = {"total": total, "prev": prev_total}
        prev_total = total

    batch = []
    for r in records:
        d = r["日期"]
        xiao = r["线索金额"]
        jiao = r["交易金额"]
        total = xiao + jiao
        prev = date_totals[d]["prev"]

        fields = {
            "日期":           ts(d),
            "线索金额":       xiao,
            "线索-短视频":    r["线索-短视频"],
            "线索-直播":      r["线索-直播"],
            "交易金额":       jiao,
            "交易-短视频":    r["交易-短视频"],
            "交易-直播":      r["交易-直播"],
            "总消耗":         total,
            "前一日消耗":     prev,
        }
        batch.append({"fields": fields})

    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/batch_create"
    headers = {"Authorization": f"Bearer {token}"}
    all_written = 0
    for i in range(0, len(batch), 20):
        chunk = batch[i:i+20]
        resp = requests.post(url, headers=headers, json={"records": chunk}, timeout=30)
        if resp.status_code not in (200, 0):
            print(f"    写入失败 [{resp.status_code}]: {resp.text[:300]}")
        else:
            all_written += len(chunk)
    return all_written

def send_group_notification(token, start_date, end_date, count):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "receive_id": GROUP_ID,
        "msg_type": "text",
        "content": json.dumps({
            "text": f"✅ 巨量引擎消耗报表写入完成\n日期：{start_date} ~ {end_date}\n写入：{count} 条\n\n📊 飞书表格：{BITABLE_MOBILE}"
        })
    }
    resp = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        headers=headers, json=payload, timeout=10)
    if resp.status_code not in (200, 0):
        print(f"  ⚠ 群通知失败 [{resp.status_code}]: {resp.text[:200]}")
    else:
        print(f"  ✓ 群通知已发送")

# ===== Dashboard HTML 生成 =====
def generate_dashboard_html(records, start_date, end_date):
    """根据 records 生成消耗报表 Dashboard HTML"""
    # 每日汇总
    daily_map = {}
    for r in records:
        d = r["日期"]
        if d not in daily_map:
            daily_map[d] = {"线索": 0, "交易": 0, "直播线索": 0, "直播交易": 0,
                           "非直线索": 0, "非直交易": 0}
        daily_map[d]["线索"] += r["线索金额"]
        daily_map[d]["交易"] += r["交易金额"]
        daily_map[d]["直播线索"] += r["线索-直播"]
        daily_map[d]["直播交易"] += r["交易-直播"]
        daily_map[d]["非直线索"] += r["线索-短视频"]
        daily_map[d]["非直交易"] += r["交易-短视频"]

    dates_sorted = sorted(daily_map.keys())
    daily_rows = []
    for d in dates_sorted:
        v = daily_map[d]
        total = v["线索"] + v["交易"]
        daily_rows.append({
            "日期_str": d,
            "线索": v["线索"], "交易": v["交易"], "合计": total,
            "直播线索": v["直播线索"], "直播交易": v["直播交易"],
            "非直线索": v["非直线索"], "非直交易": v["非直交易"],
        })

    # KPIs
    total_clue  = sum(r["线索金额"] for r in records)
    total_trade = sum(r["交易金额"] for r in records)
    total_all  = total_clue + total_trade
    clue_pct   = total_clue / total_all * 100 if total_all else 0
    trade_pct  = total_trade / total_all * 100 if total_all else 0

    live_total    = sum(r["线索-直播"] + r["交易-直播"] for r in records)
    nonlive_total = sum(r["线索-短视频"] + r["交易-短视频"] for r in records)

    if len(daily_rows) >= 2:
        prev = daily_rows[-2]
        prev_total = prev["合计"]
        prev_date  = prev["日期_str"]
    elif len(daily_rows) == 1:
        prev_total = 0
        prev_date  = daily_rows[0]["日期_str"]
    else:
        prev_total = 0
        prev_date  = ""

    # JS 数据
    dates_js        = ", ".join([f"'{d}'" for d in dates_sorted])
    clue_js         = ", ".join([f"{r['线索']:.2f}" for r in daily_rows])
    trade_js        = ", ".join([f"{r['交易']:.2f}" for r in daily_rows])
    total_js        = ", ".join([f"{r['合计']:.2f}" for r in daily_rows])
    live_clue_js    = ", ".join([f"{r['直播线索']:.2f}" for r in daily_rows])
    live_trade_js   = ", ".join([f"{r['直播交易']:.2f}" for r in daily_rows])
    nonlive_clue_js = ", ".join([f"{r['非直线索']:.2f}" for r in daily_rows])
    nonlive_trade_js= ", ".join([f"{r['非直交易']:.2f}" for r in daily_rows])

    date_range_str = f"{start_date}~{end_date}"
    update_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    table_rows = ""
    for row in daily_rows:
        pct = row["线索"] / row["合计"] * 100 if row["合计"] else 0
        table_rows += f"""      <tr>
        <td>{row['日期_str']}</td>
        <td class="num">¥{row['线索']:,.2f}</td>
        <td class="num">¥{row['交易']:,.2f}</td>
        <td class="num"><b>¥{row['合计']:,.2f}</b></td>
        <td class="num">{pct:.1f}%</td>
      </tr>
"""

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>客户消耗报表 {date_range_str}</title>
<script src="https://cdn.bootcdn.net/ajax/libs/echarts/5.4.3/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;background:#0f0f1a;color:#e8e8f0;min-height:100vh}}
.header{{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);padding:24px 40px;border-bottom:1px solid #2a2a4a}}
.header h1{{font-size:22px;font-weight:600;color:#fff;letter-spacing:1px}}
.header p{{font-size:13px;color:#8888aa;margin-top:4px}}
.kpi-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:16px;padding:24px 40px}}
.kpi-card{{background:linear-gradient(135deg,#1e1e3a 0%,#252545 100%);border-radius:12px;padding:20px 24px;border:1px solid #2e2e50;position:relative;overflow:hidden}}
.kpi-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px}}
.kpi-card.red::before{{background:linear-gradient(90deg,#e53935,#b71c1c)}}
.kpi-card.orange::before{{background:linear-gradient(90deg,#ff8c00,#ff5500)}}
.kpi-card.green::before{{background:linear-gradient(90deg,#00c853,#009624)}}
.kpi-card.blue::before{{background:linear-gradient(90deg,#0070f3,#0041b8)}}
.kpi-card.purple::before{{background:linear-gradient(90deg,#9c27b0,#6a1b9a)}}
.kpi-label{{font-size:12px;color:#8888aa;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px}}
.kpi-value{{font-size:28px;font-weight:700;color:#fff}}
.kpi-sub{{font-size:11px;color:#6666aa;margin-top:4px}}
.charts-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:0 40px 24px}}
.chart-card{{background:#1a1a2e;border-radius:12px;padding:20px;border:1px solid #2a2a4a}}
.chart-title{{font-size:14px;font-weight:600;color:#b0b0cc;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid #2a2e4a}}
.chart{{height:280px;width:100%}}
.chart-full{{grid-column:1/-1}}
.chart-full .chart{{height:320px}}
.table-card{{background:#1a1a2e;border-radius:12px;padding:20px;border:1px solid #2a2a4a;margin:0 40px 24px}}
.table-title{{font-size:14px;font-weight:600;color:#b0b0cc;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;padding:10px 12px;font-size:12px;color:#8888aa;border-bottom:1px solid #2a2a4a;font-weight:500}}
td{{padding:10px 12px;font-size:13px;color:#d0d0ee;border-bottom:1px solid #1e1e3a}}
tr:hover td{{background:#252545}}
th.num,td.num{{text-align:right}}
</style>
</head>
<body>

<div class="header">
  <h1>📊 客户消耗报表</h1>
  <p>数据周期：{date_range_str} &nbsp;|&nbsp; 更新于 {update_time}</p>
</div>

<div class="kpi-row">
  <div class="kpi-card red">
    <div class="kpi-label">前一日消耗</div>
    <div class="kpi-value">¥{prev_total:,.2f}</div>
    <div class="kpi-sub">{prev_date} 合计</div>
  </div>
  <div class="kpi-card orange">
    <div class="kpi-label">总消耗</div>
    <div class="kpi-value">¥{total_all:,.2f}</div>
    <div class="kpi-sub">线索+交易合计</div>
  </div>
  <div class="kpi-card green">
    <div class="kpi-label">本地线索消耗</div>
    <div class="kpi-value">¥{total_clue:,.2f}</div>
    <div class="kpi-sub">占比 {clue_pct:.1f}%</div>
  </div>
  <div class="kpi-card blue">
    <div class="kpi-label">本地推交易消耗</div>
    <div class="kpi-value">¥{total_trade:,.2f}</div>
    <div class="kpi-sub">占比 {trade_pct:.1f}%</div>
  </div>
  <div class="kpi-card purple">
    <div class="kpi-label">直播消耗</div>
    <div class="kpi-value">¥{live_total:,.2f}</div>
    <div class="kpi-sub">占总量 {live_total/total_all*100:.1f}%</div>
  </div>
</div>

<div class="charts-grid">
  <div class="chart-card">
    <div class="chart-title">🥧 线索 vs 交易 占比</div>
    <div id="chart1" class="chart"></div>
  </div>
  <div class="chart-card">
    <div class="chart-title">🥧 直播 vs 非直播 占比</div>
    <div id="chart2" class="chart"></div>
  </div>
  <div class="chart-card chart-full">
    <div class="chart-title">📈 每日消耗趋势</div>
    <div id="chart3" class="chart"></div>
  </div>
  <div class="chart-card chart-full">
    <div class="chart-title">📊 每日线索/交易堆叠构成</div>
    <div id="chart4" class="chart"></div>
  </div>
</div>

<div class="table-card">
  <div class="table-title">📋 每日明细（{len(daily_rows)} 天）</div>
  <table>
    <thead>
      <tr><th>日期</th><th class="num">线索消耗</th><th class="num">交易消耗</th><th class="num">合计</th><th class="num">线索占比</th></tr>
    </thead>
    <tbody>
{table_rows}    </tbody>
  </table>
</div>

<script>
var chart1 = echarts.init(document.getElementById('chart1'));
var chart2 = echarts.init(document.getElementById('chart2'));
var chart3 = echarts.init(document.getElementById('chart3'));
var chart4 = echarts.init(document.getElementById('chart4'));

var makeAxis = function() {{
  return {{
    axisLine: {{ lineStyle: {{ color: '#2a2a4a' }} }},
    axisTick: {{ show: false }},
    splitLine: {{ lineStyle: {{ color: '#1e1e3a', type: 'dashed' }} }},
    axisLabel: {{ color: '#8888aa' }}
  }};
}};

chart1.setOption({{
  tooltip: {{ trigger: 'item', formatter: '{{b}}: ¥{{c}} ({{d}}%)' }},
  legend: {{ orient: 'vertical', right: 10, top: 'center', textStyle: {{ color: '#8888aa' }} }},
  series: [{{
    type: 'pie', radius: ['40%', '70%'], center: ['40%', '50%'],
    label: {{ color: '#d0d0ee', formatter: '{{b}}\\n¥{{c}}' }},
    data: [
      {{ value: {total_clue:.2f}, name: '线索消耗', itemStyle: {{ color: '#00c853' }} }},
      {{ value: {total_trade:.2f}, name: '交易消耗', itemStyle: {{ color: '#0070f3' }} }}
    ]
  }}]
}});

chart2.setOption({{
  tooltip: {{ trigger: 'item', formatter: '{{b}}: ¥{{c}} ({{d}}%)' }},
  legend: {{ orient: 'vertical', right: 10, top: 'center', textStyle: {{ color: '#8888aa' }} }},
  series: [{{
    type: 'pie', radius: ['40%', '70%'], center: ['40%', '50%'],
    label: {{ color: '#d0d0ee', formatter: '{{b}}\\n¥{{c}}' }},
    data: [
      {{ value: {live_total:.2f}, name: '直播计划', itemStyle: {{ color: '#ff6d00' }} }},
      {{ value: {nonlive_total:.2f}, name: '非直播计划', itemStyle: {{ color: '#7c4dff' }} }}
    ]
  }}]
}});

chart3.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }}, formatter: function(params) {{
    var date = params[0].name;
    var items = params.map(function(p) {{ return p.marker + p.seriesName + ': ¥' + p.value.toLocaleString(); }}).join('<br/>');
    return date + '<br/>' + items;
  }}}},
  legend: {{ data: ['线索消耗','交易消耗','合计'], textStyle: {{ color: '#8888aa' }}, top: 5 }},
  grid: {{ left: 80, right: 40, top: 40, bottom: 30 }},
  xAxis: {{ type: 'category', data: [{dates_js}], ...makeAxis(), axisLabel: {{ fontSize: 11 }} }},
  yAxis: {{ type: 'value', ...makeAxis(), axisLabel: {{ formatter: '¥{{value}}' }} }},
  series: [
    {{ name: '线索消耗', type: 'line', data: [{clue_js}], smooth: true, lineStyle: {{ color: '#00c853', width: 2 }}, itemStyle: {{ color: '#00c853' }} }},
    {{ name: '交易消耗', type: 'line', data: [{trade_js}], smooth: true, lineStyle: {{ color: '#0070f3', width: 2 }}, itemStyle: {{ color: '#0070f3' }} }},
    {{ name: '合计', type: 'line', data: [{total_js}], smooth: true, lineStyle: {{ color: '#ff8c00', width: 2, type: 'dashed' }}, itemStyle: {{ color: '#ff8c00' }} }}
  ]
}});

chart4.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'stack' }}, formatter: function(params) {{
    var date = params[0].name;
    var vals = params.map(function(p) {{ return p.marker + p.seriesName + ': ¥' + Number(p.value).toLocaleString(); }}).join('<br/>');
    return date + '<br/>' + vals;
  }}}},
  legend: {{ data: ['直播-线索','直播-交易','非直播-线索','非直播-交易'], textStyle: {{ color: '#8888aa' }}, top: 5 }},
  grid: {{ left: 80, right: 20, top: 40, bottom: 30 }},
  xAxis: {{ type: 'category', data: [{dates_js}], ...makeAxis(), axisLabel: {{ fontSize: 11 }} }},
  yAxis: {{ type: 'value', ...makeAxis(), axisLabel: {{ formatter: '¥{{value}}' }} }},
  series: [
    {{ name: '直播-线索', type: 'bar', stack: 'live', data: [{live_clue_js}], itemStyle: {{ color: '#ff6d00' }} }},
    {{ name: '直播-交易', type: 'bar', stack: 'live', data: [{live_trade_js}], itemStyle: {{ color: '#ff9100' }} }},
    {{ name: '非直播-线索', type: 'bar', stack: 'nonlive', data: [{nonlive_clue_js}], itemStyle: {{ color: '#7c4dff' }} }},
    {{ name: '非直播-交易', type: 'bar', stack: 'nonlive', data: [{nonlive_trade_js}], itemStyle: {{ color: '#b47cff' }} }}
  ]
}});
</script>
</body>
</html>"""
    return html

# ===== GitHub Push =====
def push_dashboard_to_github(html_content):
    """将 Dashboard HTML 推送到 GitHub 仓库的 index.html"""
    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    api_url = f"https://api.github.com/repos/{GH_REPO}/contents/{GH_HTML_PATH}"

    # 获取当前 SHA
    get_req = urllib.request.Request(api_url, headers=headers)
    sha = None
    try:
        with urllib.request.urlopen(get_req) as r:
            resp_data = json.loads(r.read())
            sha = resp_data.get("sha")
            print(f"  当前 index.html SHA: {sha[:10]}...")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("  index.html 不存在，将创建新文件")
        else:
            print(f"  ⚠ 获取 SHA 失败: {e.code}")
            return False
    except Exception as e:
        print(f"  ⚠ 获取 SHA 异常: {e}")
        return False

    # 推送
    payload = {
        "message": f"Update consumption dashboard: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": base64.b64encode(html_content.encode("utf-8")).decode("ascii"),
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
    try:
        with urllib.request.urlopen(put_req) as r:
            result = json.loads(r.read())
        commit = result.get("commit", {})
        commit_sha = commit.get("sha", "unknown")[:10]
        print(f"  ✅ Dashboard 已推送 GitHub SHA: {commit_sha}")
        print(f"     → https://consumption-dashboard.pages.dev")
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        print(f"  ⚠ GitHub push 失败 [{e.code}]: {body}")
        return False
    except Exception as e:
        print(f"  ⚠ GitHub push 异常: {e}")
        return False

# ===== 主流程 =====
def main():
    excel_path = find_latest_excel()
    if not excel_path:
        print("错误：未找到Excel文件，请先运行 ocean_daily.py 下载报表")
        sys.exit(1)

    print(f"读取Excel：{excel_path}")
    records = read_and_aggregate(excel_path)
    if not records:
        print("错误：Excel无数据")
        sys.exit(1)

    dates = sorted(set(r["日期"] for r in records))
    start_date = dates[0] if dates else str(date.today().replace(day=1))
    end_date   = dates[-1] if dates else str(date.today() - timedelta(days=1))
    print(f"日期范围：{start_date} ~ {end_date}，聚合后 {len(records)} 条账户×日记录")

    token = get_app_token()
    print("写入飞书多维表格…")
    count = write_records(token, records, start_date, end_date)
    print(f"写入完成：{count} 条")

    # 生成 Dashboard HTML 并推送到 GitHub
    print("生成 Dashboard HTML…")
    html = generate_dashboard_html(records, start_date, end_date)
    push_ok = push_dashboard_to_github(html)

    if push_ok:
        print("全部完成！")
    else:
        print("⚠ Dashboard 推送失败，飞书写入已完成")

if __name__ == "__main__":
    main()
