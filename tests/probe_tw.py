# -*- coding: utf-8 -*-
"""探測臺指VIX日資料、期交所下載區間上限"""
import re, requests
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
h = requests.get("https://www.taifex.com.tw/cht/7/vixDaily3MNew", headers=UA, timeout=30).text
print("##### vixDaily3MNew 頁面長度", len(h))
for l in sorted(set(re.findall(r'(?:href|action|src|value)="([^"]+)"', h))):
    if re.search(r"vix|down|txt|csv|zip|Dailydownload", l, re.I): print("  ", l)
txt = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S)
txt = re.sub(r"<[^>]+>", " ", txt); txt = re.sub(r"\s+", " ", txt)
i = txt.find("VIX"); print("文字片段：", txt[max(0,i-200):i+1500])

for url in ["https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/2026/20260717new.txt",
            "https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/20260717new.txt",
            "https://www.taifex.com.tw/cht/7/vixDailyDown"]:
    try:
        r = requests.get(url, headers=UA, timeout=30)
        print(f"\n##### {url}\nHTTP {r.status_code} 長度 {len(r.content)}\n{r.content[:300]!r}")
    except Exception as e: print(url, e)

print("\n##### 期交所三大法人下載：3 年區間")
r = requests.post("https://www.taifex.com.tw/cht/3/futContractsDateDown", headers=UA, timeout=60,
                  data={"queryStartDate": "2023/10/01", "queryEndDate": "2026/10/16", "commodityId": "TXF"})
t = r.content.decode("big5", errors="replace"); lines = t.strip().splitlines()
print("HTTP", r.status_code, "行數", len(lines)); print(lines[:2]); print(lines[-2:])
