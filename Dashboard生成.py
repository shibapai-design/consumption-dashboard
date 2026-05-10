#!/usr/bin/env python3
"""
Dashboard生成.py — 读取分日消耗报表Excel，生成可视化 Dashboard HTML
用法: python3 Dashboard生成.py --file <Excel路径> [--output <输出路径>]
"""
import argparse, os, sys
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas not installed")
    sys.exit(1)


def parse_date_range(dates):
    dates_sorted = sorted(set(dates))
    if len(dates_sorted) == 1:
        return dates_sorted[0]
    return f"{dates_sorted[0]}~{dates_sorted[-1]}"


def generate_html(df, date_range_str, output_path):
    # ── 聚合 ────────────────────────────────────────────────
    # 每日汇总
    daily = df.groupby("日期_str").agg(
        线索=("本地线索消耗", "sum"),
        交易=("本地推交易消耗", "sum"),
    ).reset_index()
    daily["合计"] = daily["线索"] + daily["交易"]
    daily = daily.sort_values("日期_str")

    # 月度汇总
    total_clue   = df["本地线索消耗"].sum()
    total_trade  = df["本地推交易消耗"].sum()
    total_all    = total_clue + total_trade
    clue_pct     = total_clue / total_all * 100 if total_all else 0
    trade_pct    = total_trade / total_all * 100 if total_all else 0

    # 直播 vs 非直播
    live_df     = df[df["推广形式"] == "直播计划"]
    nonlive_df  = df[df["推广形式"] == "非直播计划"]
    live_clue   = live_df["本地线索消耗"].sum()
    live_trade  = live_df["本地推交易消耗"].sum()
    nonlive_clue= nonlive_df["本地线索消耗"].sum()
    nonlive_trade= nonlive_df["本地推交易消耗"].sum()
    live_total  = live_clue + live_trade
    nonlive_total = nonlive_clue + nonlive_trade

    # 每日直播/非直播
    live_daily = df[df["推广形式"] == "直播计划"].groupby("日期_str").agg(
        线索=("本地线索消耗", "sum"), 交易=("本地推交易消耗", "sum")
    ).reset_index().rename(columns={"线索": "直播线索", "交易": "直播交易"})
    nonlive_daily = df[df["推广形式"] == "非直播计划"].groupby("日期_str").agg(
        线索=("本地线索消耗", "sum"), 交易=("本地推交易消耗", "sum")
    ).reset_index().rename(columns={"线索": "非直线索", "交易": "非直交易"})
    day_df = daily.merge(live_daily, on="日期_str", how="left").merge(nonlive_daily, on="日期_str", how="left").fillna(0)

    # ── JS 数据串 ───────────────────────────────────────────
    dates_js    = ", ".join([f"'{d}'" for d in daily["日期_str"]])
    clue_js     = ", ".join([f"{v:.2f}" for v in daily["线索"]])
    trade_js    = ", ".join([f"{v:.2f}" for v in daily["交易"]])
    total_js    = ", ".join([f"{v:.2f}" for v in daily["合计"]])

    live_clue_js    = ", ".join([f"{v:.2f}" for v in day_df["直播线索"]])
    live_trade_js   = ", ".join([f"{v:.2f}" for v in day_df["直播交易"]])
    nonlive_clue_js = ", ".join([f"{v:.2f}" for v in day_df["非直线索"]])
    nonlive_trade_js= ", ".join([f"{v:.2f}" for v in day_df["非直交易"]])

    update_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── HTML ─────────────────────────────────────────────────
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
.kpi-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;padding:24px 40px}}
.kpi-card{{background:linear-gradient(135deg,#1e1e3a 0%,#252545 100%);border-radius:12px;padding:20px 24px;border:1px solid #2e2e50;position:relative;overflow:hidden}}
.kpi-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px}}
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
  <div class="table-title">📋 每日明细（{len(daily)} 天）</div>
  <table>
    <thead>
      <tr><th>日期</th><th class="num">线索消耗</th><th class="num">交易消耗</th><th class="num">合计</th><th class="num">线索占比</th></tr>
    </thead>
    <tbody>
"""
    for _, row in daily.iterrows():
        pct = row["线索"]/row["合计"]*100 if row["合计"] else 0
        html += f"""      <tr>
        <td>{row["日期_str"]}</td>
        <td class="num">¥{row["线索"]:,.2f}</td>
        <td class="num">¥{row["交易"]:,.2f}</td>
        <td class="num"><b>¥{row["合计"]:,.2f}</b></td>
        <td class="num">{pct:.1f}%</td>
      </tr>
"""
    html += """    </tbody>
  </table>
</div>

<script>
var chart1 = echarts.init(document.getElementById('chart1'));
var chart2 = echarts.init(document.getElementById('chart2'));
var chart3 = echarts.init(document.getElementById('chart3'));
var chart4 = echarts.init(document.getElementById('chart4'));

var makeAxis = function() {
  return {
    axisLine: { lineStyle: { color: '#2a2a4a' } },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: '#1e1e3a', type: 'dashed' } },
    axisLabel: { color: '#8888aa' }
  };
};

chart1.setOption({
  tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
  legend: { orient: 'vertical', right: 10, top: 'center', textStyle: { color: '#8888aa' } },
  series: [{
    type: 'pie', radius: ['40%', '70%'], center: ['40%', '50%'],
    label: { color: '#d0d0ee', formatter: '{b}\\n¥{c}' },
    data: [
      { value: """ + f"{total_clue:.2f}" + """, name: '线索消耗', itemStyle: { color: '#00c853' } },
      { value: """ + f"{total_trade:.2f}" + """, name: '交易消耗', itemStyle: { color: '#0070f3' } }
    ]
  }]
});

chart2.setOption({
  tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
  legend: { orient: 'vertical', right: 10, top: 'center', textStyle: { color: '#8888aa' } },
  series: [{
    type: 'pie', radius: ['40%', '70%'], center: ['40%', '50%'],
    label: { color: '#d0d0ee', formatter: '{b}\\n¥{c}' },
    data: [
      { value: """ + f"{live_total:.2f}" + """, name: '直播计划', itemStyle: { color: '#ff6d00' } },
      { value: """ + f"{nonlive_total:.2f}" + """, name: '非直播计划', itemStyle: { color: '#7c4dff' } }
    ]
  }]
});

chart3.setOption({
  tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, formatter: function(params) {
    var date = params[0].name;
    var items = params.map(function(p) { return p.marker + p.seriesName + ': ¥' + p.value.toLocaleString(); }).join('<br/>');
    return date + '<br/>' + items;
  }},
  legend: { data: ['线索消耗','交易消耗','合计'], textStyle: { color: '#8888aa' }, top: 5 },
  grid: { left: 80, right: 40, top: 40, bottom: 30 },
  xAxis: { type: 'category', data: [""" + dates_js + """], ...makeAxis(), axisLabel: { fontSize: 11 } },
  yAxis: { type: 'value', ...makeAxis(), axisLabel: { formatter: '¥{value}' } },
  series: [
    { name: '线索消耗', type: 'line', data: [""" + clue_js + """], smooth: true, lineStyle: { color: '#00c853', width: 2 }, itemStyle: { color: '#00c853' } },
    { name: '交易消耗', type: 'line', data: [""" + trade_js + """], smooth: true, lineStyle: { color: '#0070f3', width: 2 }, itemStyle: { color: '#0070f3' } },
    { name: '合计', type: 'line', data: [""" + total_js + """], smooth: true, lineStyle: { color: '#ff8c00', width: 2, type: 'dashed' }, itemStyle: { color: '#ff8c00' } }
  ]
});

chart4.setOption({
  tooltip: { trigger: 'axis', axisPointer: { type: 'stack' }, formatter: function(params) {
    var date = params[0].name;
    var vals = params.map(function(p) { return p.marker + p.seriesName + ': ¥' + Number(p.value).toLocaleString(); }).join('<br/>');
    return date + '<br/>' + vals;
  }},
  legend: { data: ['直播-线索','直播-交易','非直播-线索','非直播-交易'], textStyle: { color: '#8888aa' }, top: 5 },
  grid: { left: 80, right: 20, top: 40, bottom: 30 },
  xAxis: { type: 'category', data: [""" + dates_js + """], ...makeAxis(), axisLabel: { fontSize: 11 } },
  yAxis: { type: 'value', ...makeAxis(), axisLabel: { formatter: '¥{value}' } },
  series: [
    { name: '直播-线索', type: 'bar', stack: 'live', data: [""" + live_clue_js + """], itemStyle: { color: '#ff6d00' } },
    { name: '直播-交易', type: 'bar', stack: 'live', data: [""" + live_trade_js + """], itemStyle: { color: '#ff9100' } },
    { name: '非直播-线索', type: 'bar', stack: 'nonlive', data: [""" + nonlive_clue_js + """], itemStyle: { color: '#7c4dff' } },
    { name: '非直播-交易', type: 'bar', stack: 'nonlive', data: [""" + nonlive_trade_js + """], itemStyle: { color: '#b47cff' } }
  ]
});

window.addEventListener('resize', function() {
  chart1.resize(); chart2.resize(); chart3.resize(); chart4.resize();
});
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard 已生成: {output_path} ({len(html)} bytes)")
    return output_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--output", help="输出 HTML 路径（默认同目录 <原文件名>_dashboard.html）")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"文件不存在: {args.file}")
        sys.exit(1)

    df = pd.read_excel(args.file, header=0)
    print(f"读取 {len(df)} 行，列: {df.columns.tolist()}")

    required = ["时间", "本地线索消耗", "本地推交易消耗", "推广形式"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"缺少列: {missing}")
        sys.exit(1)

    df["日期_str"] = pd.to_datetime(df["时间"]).dt.strftime("%Y-%m-%d")
    date_range_str = parse_date_range(df["日期_str"])

    if args.output:
        output_path = args.output
    else:
        base = os.path.splitext(os.path.basename(args.file))[0]
        output_path = os.path.join(os.path.dirname(args.file), f"{base}_dashboard.html")

    generate_html(df, date_range_str, output_path)


if __name__ == "__main__":
    main()
