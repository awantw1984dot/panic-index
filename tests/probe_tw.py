import io, zipfile, requests, urllib.parse
UA = {"User-Agent": "Mozilla/5.0"}
for ym in ["202310", "202407", "202504", "202601", "202606"]:
    fn = urllib.parse.quote(f"{ym}歷史紀錄波動率指數_新VIX.zip")
    for base in ["logdata", "logdata/" + ym[:4]]:
        u = f"https://www.taifex.com.tw/file/taifex/Dailydownload/vix/{base}/{fn}"
        r = requests.get(u, headers=UA, timeout=60)
        ok = r.content[:2] == b"PK"
        print(ym, base, r.status_code, len(r.content), "ZIP" if ok else "非ZIP")
        if ok:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            names = z.namelist(); print("  檔案：", names[:5], len(names))
            t = z.read(names[0]).decode("big5", errors="replace")
            print("  開頭：", repr(t[:300])); print("  結尾：", repr(t[-200:]))
            break
