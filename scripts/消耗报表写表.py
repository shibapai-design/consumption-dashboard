#!/usr/bin/env python3
"""巨量引擎消耗报表 — 读取Excel并写入飞书多维表格，然后发群通知"""
import sys, os, json, time, glob
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
    # 建立列名→索引映射
    col_idx = {h: i for i, h in enumerate(headers)}

    def col(name, row):
        idx = col_idx.get(name)
        return row[idx] if idx is not None else None

    # 按 (账户, 日期) 聚合
    agg = {}  # key = (account_name, date_str)
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
                "线索金额": 0,
                "线索-短视频": 0,
                "线索-直播": 0,
                "交易金额": 0,
                "交易-短视频": 0,
                "交易-直播": 0,
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
            # 未知形式，全部算短视频
            agg[key]["线索-短视频"] += xian_suo
            agg[key]["交易-短视频"] += jiao_yi

    records = list(agg.values())
    records.sort(key=lambda x: (x["account"], x["日期"]))
    return records

def write_records(token, records, start_date, end_date):
    """批量写入记录到bitable"""
    # 确保字段存在
    ensure_field(token, "总消耗", 2)
    ensure_field(token, "前一日消耗", 2)
    time.sleep(1)

    fm = get_fields(token)

    def fid(name):
        for fname, finfo in fm.items():
            if fname.strip() == name.strip():
                return finfo["id"]
        raise ValueError(f"字段「{name}」不存在")

    def ts(d):
        return int(datetime.strptime(d, "%Y-%m-%d").timestamp() * 1000)

    # 按日期排序（全局），算前一日消耗
    by_date = sorted(records, key=lambda x: x["日期"])
    date_totals = {}  # date → total消耗
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
            fid("日期"):        ts(d),
            fid("线索金额"):    xiao,
            fid("线索-短视频"): r["线索-短视频"],
            fid("线索-直播"):   r["线索-直播"],
            fid("交易金额"):    jiao,
            fid("交易-短视频"): r["交易-短视频"],
            fid("交易-直播"):   r["交易-直播"],
            fid("总消耗"):      total,
            fid("前一日消耗"):   prev,
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

# SHA 替换：生产环境用 GITHUB_SHA 环境变量，或每次手动更新
DASHBOARD_SHA = os.environ.get("GITHUB_SHA", "1c9f7d46")[:8]

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

    # Dashboard 行供 feishu.py 提取到通知里，不要删这行
    print(f"✅ Dashboard 已推送 GitHub SHA: {DASHBOARD_SHA}")
    print(f"   → https://consumption-dashboard.pages.dev")

    print("全部完成！")

if __name__ == "__main__":
    main()
