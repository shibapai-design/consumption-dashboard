#!/usr/bin/env python3
"""
本地推商户监控 — 主程序
遍历所有商户采集数据 → 写入飞书 → 保存JSON → 发群通知
"""
import sys, os, json, subprocess, time
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

# 飞书配置
APP_TOKEN  = "W6apbYhDjaQjDbs83K8cWb1hnce"
TABLE_ID   = "tblgcjlG9IQEt8iT"
GROUP_ID   = "oc_8f778f85cc100c6b64fec995d1be5ffc"
BOT_APP_ID = "cli_a976b9b729fa9bb3"
BOT_SECRET = "k0lyGolc88vm59YTHkBohcHmTJjcA5Ub"
BITABLE_MOBILE = "https://mxc4p3lj7pi.feishu.cn/base/W6apbYhDjaQjDbs83K8cWb1hnce?table=tblgcjlG9IQEt8iT&view=vewJBY0aLT"

def get_token():
    import requests
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": BOT_APP_ID, "app_secret": BOT_SECRET}, timeout=10
    )
    return r.json()["tenant_access_token"]

def get_merchant_records(token):
    import requests
    r = requests.get(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records?page_size=100",
        headers={"Authorization": f"Bearer {token}"}, timeout=10
    )
    m = {}
    for rec in r.json().get("data", {}).get("items", []):
        name = rec.get("fields", {}).get("商户名称", "")
        if name:
            m[name] = rec["record_id"]
    return m

def write_record(token, record_id, fields_data):
    import requests
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/{record_id}"
    r = requests.put(url, headers={"Authorization": f"Bearer {token}"}, json={"fields": fields_data}, timeout=10)
    return r

def send_notification(token, ok, total, err_msg=""):
    import requests
    status = "✅" if not err_msg else "⚠️"
    text = f"""📊 本地推商户监控已更新

{status} 成功采集: {ok}/{total} 商户
⏰ 更新时间: {datetime.now().strftime('%H:%M:%S')}
📊 飞书表格: {BITABLE_MOBILE}"""
    if err_msg:
        text += f"\n⚠️ 错误: {err_msg[:100]}"
    payload = {"receive_id": GROUP_ID, "msg_type": "text", "content": json.dumps({"text": text})}
    r = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload, timeout=10
    )

def main():
    print(f"开始采集 {len(MERCHANTS)} 个商户... {datetime.now().strftime('%H:%M:%S')}")
    
    results = {}
    errors = []
    
    for i, name in enumerate(MERCHANTS):
        print(f"\n[{i+1}/{len(MERCHANTS)}] {name}...", end=" ", flush=True)
        
        # 调用子进程采集
        r = subprocess.run(
            [sys.executable, "/tmp/merchant_collect.py", name],
            capture_output=True, text=True, timeout=90
        )
        
        if r.returncode == 0 and r.stdout.strip():
            try:
                data = json.loads(r.stdout.strip())
                results[name] = data
                print(f"✅ 余额={data.get('可用余额')} 消耗={data.get('实时消耗')}")
            except:
                print(f"⚠️ 解析失败: {r.stdout[:50]}")
                errors.append(f"{name}: 解析失败")
        else:
            print(f"❌ {r.stderr[:80] if r.stderr else '超时'}")
            errors.append(f"{name}: {r.stderr[:50] if r.stderr else '超时'}")
        
        # 每个商户间隔2秒
        if i < len(MERCHANTS) - 1:
            time.sleep(2)
    
    print(f"\n采集完成: {len(results)}/{len(MERCHANTS)} 成功")
    
    # 写入飞书
    if results:
        token = get_token()
        record_map = get_merchant_records(token)
        today_str = datetime.now().strftime("%Y-%m-%d")
        date_ms = int(datetime.strptime(today_str, "%Y-%m-%d").timestamp() * 1000)
        now_ms = int(datetime.now().timestamp() * 1000)
        
        write_ok = 0
        for name, data in results.items():
            rid = record_map.get(name)
            if not rid:
                print(f"  ⚠️ 未找到记录: {name}")
                continue
            
            fields = {
                "日期": date_ms,
                "实时消耗": data.get("实时消耗", 0),
                "消耗_短视频": data.get("消耗_短视频", 0),
                "消耗_直播": data.get("消耗_直播", 0),
                "转化数": data.get("转化数", 0),
                "转化成本": data.get("转化成本", 0),
                "可用余额": data.get("可用余额", 0),
                "更新时间": now_ms,
            }
            
            resp = write_record(token, rid, fields)
            if resp.status_code in (200, 0):
                write_ok += 1
            else:
                print(f"  ⚠️ 写入失败 {name}: {resp.status_code}")
        
        print(f"飞书写入: {write_ok}/{len(results)} 成功")
    else:
        print("无数据，跳过飞书写入")
    
    # 保存JSON
    output = {
        "update_time": datetime.now().isoformat(),
        "merchants": [{"name": k, **v} for k, v in results.items()]
    }
    with open("/tmp/merchant_data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON已保存: /tmp/merchant_data.json ({len(results)}条)")
    
    # 发群通知
    try:
        token = get_token()
        err_text = "; ".join(errors[:2])
        send_notification(token, len(results), len(MERCHANTS), err_text)
        print("✅ 群通知已发送")
    except Exception as e:
        print(f"⚠️ 通知失败: {e}")

if __name__ == "__main__":
    main()
