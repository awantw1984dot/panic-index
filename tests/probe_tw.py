# -*- coding: utf-8 -*-
"""探測臺指VIX歷史檔案"""
import re, requests
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
for page in ["vixMinNew", "vixDaily3MNew", "vixMin3MNew"]:
    h = requests.get(f"https://www.taifex.com.tw/cht/7/{page}", headers=UA, timeout=30).text
    print(f"##### {page}")
    for m in sorted(set(re.findall(r"[\w/\.\-]*(?:Dailydownload|log2data|\.txt|\.zip|\.csv)[\w/\.\-]*", h))):
        print("  路徑：", m)
    for m in re.finditer(r"(?:download|Down|file)[^\n]{0,160}", h):
        s = m.group(0)
        if "pic_banners" not in s and "CHINESE/1" not in s: print("  片段：", s[:160])
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", h, flags=re.S)
    cells = [re.sub(r"<[^>]+>|\s+", " ", r).strip() for r in rows]
    vixrows = [c for c in cells if re.match(r"20\d\d/\d\d/\d\d", c)]
    print("  日期列數：", len(vixrows), vixrows[:3], vixrows[-2:])
for u in ["https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/202607new.txt",
          "https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/2026/202607new.txt",
          "https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/202607new.zip",
          "https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/2026/202607new.zip"]:
    r = requests.get(u, headers=UA, timeout=30)
    print(u, r.status_code, len(r.content), r.content[:80])
