# -*- coding: utf-8 -*-
"""
連線測試：確認 GitHub Actions 主機能否抓到各資料來源
每個來源回報：HTTP 狀態、回應大小、內容是否像真資料
"""
import datetime as dt
import sys
import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

# 找最近一個平日當測試日期（避開週末）
d = dt.date.today() - dt.timedelta(days=1)
while d.weekday() >= 5:
    d -= dt.timedelta(days=1)
ymd = d.strftime("%Y%m%d")
ymd_slash = d.strftime("%Y/%m/%d")

TESTS = [
    # (分組, 名稱, URL, 判斷內容正常的關鍵字)
    ("美股", "Yahoo VIX", "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?range=5d&interval=1d", "regularMarketPrice"),
    ("美股", "Yahoo VIX3M", "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX3M?range=5d&interval=1d", "regularMarketPrice"),
    ("美股", "Yahoo MOVE", "https://query1.finance.yahoo.com/v8/finance/chart/%5EMOVE?range=5d&interval=1d", "regularMarketPrice"),
    ("美股", "FRED HY利差", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2&cosd=2026-09-01", "BAMLH0A0HYM2"),
    ("美股", "FRED IG利差", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLC0A0CM&cosd=2026-09-01", "BAMLC0A0CM"),
    ("美股", "FRED STLFSI", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=STLFSI4&cosd=2026-06-01", "STLFSI4"),
    ("台股", "證交所 融資融券彙總", f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={ymd}&selectType=MS&response=json", "融資"),
    ("台股", "證交所 個股融資(全部)", f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={ymd}&selectType=ALL&response=json", "stat"),
    ("台股", "證交所 全市場收盤價", f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json", "stat"),
    ("台股", "證交所 OpenAPI", "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN", "["),
    ("台股", "櫃買中心", "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_balance", "["),
    ("台股", "期交所 三大法人期貨", f"https://www.taifex.com.tw/cht/3/futContractsDate?queryDate={ymd_slash}", "臺股期貨"),
    ("台股", "期交所 OpenAPI", "https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate", "["),
    ("台股", "期交所 臺指VIX", "https://www.taifex.com.tw/cht/7/vixMinNew", "VIX"),
]

print(f"測試日期：{ymd}　執行時間（UTC）：{dt.datetime.utcnow():%Y-%m-%d %H:%M}\n")
results = []
for group, name, url, key in TESTS:
    try:
        r = requests.get(url, headers=UA, timeout=20)
        body = r.text
        ok = r.status_code == 200 and key in body
        status = "通過" if ok else f"異常（HTTP {r.status_code}，{'有' if key in body else '無'}預期內容）"
        snippet = body[:80].replace("\n", " ")
    except Exception as e:
        ok, status, snippet = False, f"失敗：{type(e).__name__}", str(e)[:80]
    results.append((group, name, ok))
    print(f"[{'O' if ok else 'X'}] {group}｜{name}｜{status}")
    if not ok:
        print(f"      回應開頭：{snippet}")

print("\n=== 總結 ===")
for g in ["美股", "台股"]:
    sub = [r for r in results if r[0] == g]
    n_ok = sum(r[2] for r in sub)
    print(f"{g}：{n_ok}/{len(sub)} 通過")
fails = [r[1] for r in results if not r[2]]
print("未通過：" + ("、".join(fails) if fails else "無"))
