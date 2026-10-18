# -*- coding: utf-8 -*-
"""探測台股歷史資料端點格式"""
import json, re, time, requests
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
D = "20260717"

def twse(url):
    r = requests.get(url, headers=UA, timeout=30); time.sleep(3)
    return r.json()

def show_twse(name, j):
    print(f"\n##### {name}")
    print("頂層鍵：", list(j.keys()))
    if "tables" in j:
        for t in j["tables"]:
            print(f"-- 表：{t.get('title')}｜欄位：{t.get('fields')}")
            for row in (t.get("data") or [])[:3]:
                print("   ", row)
            print(f"   （共 {len(t.get('data') or [])} 列）")
    else:
        print("欄位：", j.get("fields")); 
        for row in (j.get("data") or [])[:3]: print("   ", row)
        print(f"   （共 {len(j.get('data') or [])} 列）")
        for k in ["creditFields", "creditList"]:
            if k in j: print(k, str(j[k])[:300])

for name, url in [
    ("MI_MARGN MS", f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={D}&selectType=MS&response=json"),
    ("MI_MARGN ALL", f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={D}&selectType=ALL&response=json"),
    ("MI_INDEX ALLBUT0999", f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={D}&type=ALLBUT0999&response=json"),
    ("FMTQIK 月成交與指數", f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={D}&response=json"),
]:
    try: show_twse(name, twse(url))
    except Exception as e: print(f"\n##### {name} 失敗 {type(e).__name__} {e}")

print("\n##### 期交所 三大法人期貨區間下載 TXF")
try:
    r = requests.post("https://www.taifex.com.tw/cht/3/futContractsDateDown", headers=UA, timeout=30,
                      data={"queryStartDate": "2026/07/01", "queryEndDate": "2026/07/31", "commodityId": "TXF"})
    for enc in ["utf-8", "big5", "cp950"]:
        try: txt = r.content.decode(enc); break
        except: continue
    print("HTTP", r.status_code, "編碼", enc, "長度", len(txt)); print(txt[:900])
except Exception as e: print("失敗", e)

print("\n##### 期交所 OpenAPI swagger 中與 VIX / 三大法人 相關的路徑")
try:
    sw = requests.get("https://openapi.taifex.com.tw/swagger.json", headers=UA, timeout=30).json()
    for p, v in sw.get("paths", {}).items():
        s = json.dumps(v, ensure_ascii=False)
        if re.search(r"VIX|波動率|Institutional|法人", p + s, re.I):
            print(p, "｜", (v.get("get", {}).get("summary") or "")[:60])
except Exception as e: print("失敗", e)

print("\n##### 期交所 vixMinNew 頁面中的連結")
try:
    h = requests.get("https://www.taifex.com.tw/cht/7/vixMinNew", headers=UA, timeout=30).text
    links = sorted(set(re.findall(r'(?:href|action|src)="([^"]+)"', h)))
    for l in links:
        if re.search(r"vix|down|file|csv|txt", l, re.I): print("  ", l)
    for m in re.finditer(r"<form[^>]*>", h): print("  FORM", m.group(0)[:200])
except Exception as e: print("失敗", e)
