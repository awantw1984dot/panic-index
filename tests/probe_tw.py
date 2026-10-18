import requests
UA = {"User-Agent": "Mozilla/5.0"}
r = requests.get("https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/202607new.txt", headers=UA, timeout=30)
t = r.content.decode("big5", errors="replace")
print(repr(t[:700]))
for y in ["202310", "202401", "202504", "202606"]:
    r = requests.get(f"https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/{y}new.txt", headers=UA, timeout=30)
    print(y, r.status_code, len(r.content), repr(r.content[:60]))
