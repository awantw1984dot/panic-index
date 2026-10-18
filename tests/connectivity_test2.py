# -*- coding: utf-8 -*-
"""第二輪：美股替代來源"""
import requests, time
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

def show(name, ok, info):
    print(f"[{'O' if ok else 'X'}] {name}｜{info}")

# 1. yfinance 套件（內建瀏覽器模擬，常能繞過 429）
try:
    import yfinance as yf
    for t in ["^VIX", "^VIX3M", "^MOVE", "JNK", "IEF", "^GSPC"]:
        df = yf.download(t, period="1mo", progress=False, auto_adjust=True)
        ok = len(df) > 5
        show(f"yfinance {t}", ok, f"{len(df)} 筆" + (f"，最新 {float(df['Close'].iloc[-1].iloc[0] if hasattr(df['Close'].iloc[-1],'iloc') else df['Close'].iloc[-1]):.2f}" if ok else ""))
        time.sleep(1)
except Exception as e:
    show("yfinance", False, f"{type(e).__name__}: {str(e)[:100]}")

# 2. CBOE 官方 CSV（VIX、VIX3M 完整歷史）
for t in ["VIX", "VIX3M"]:
    url = f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{t}_History.csv"
    try:
        r = requests.get(url, headers=UA, timeout=30)
        lines = r.text.strip().splitlines()
        ok = r.status_code == 200 and len(lines) > 100
        show(f"CBOE {t}", ok, f"HTTP {r.status_code}，{len(lines)} 行，最後一行 {lines[-1] if lines else ''}")
    except Exception as e:
        show(f"CBOE {t}", False, f"{type(e).__name__}")

# 3. FRED：不同網址、較長等待時間
fred_urls = {
    "FRED csv 長逾時": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2",
    "FRED API(無金鑰)": "https://api.stlouisfed.org/fred/series/observations?series_id=BAMLH0A0HYM2&file_type=json",
    "FRED 下載頁": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2/downloaddata/BAMLH0A0HYM2.csv",
}
for name, url in fred_urls.items():
    try:
        r = requests.get(url, headers=UA, timeout=60)
        show(name, r.status_code == 200, f"HTTP {r.status_code}，開頭 {r.text[:70]!r}")
    except Exception as e:
        show(name, False, f"{type(e).__name__}")
