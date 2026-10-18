# -*- coding: utf-8 -*-
"""第三輪：FRED API 金鑰驗證與歷史長度（不印出金鑰）"""
import os, requests
key = os.environ.get("FRED_API_KEY", "")
print(f"金鑰長度：{len(key)}（應為 32）")
for sid, name in [("BAMLH0A0HYM2", "HY 利差"), ("BAMLC0A0CM", "IG 利差"), ("STLFSI4", "STLFSI"),
                  ("DGS10", "10年期殖利率（對照用）")]:
    try:
        r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                         params={"series_id": sid, "api_key": key, "file_type": "json"}, timeout=60)
        if r.status_code != 200:
            print(f"[X] {name}｜HTTP {r.status_code}｜{r.text[:120]}")
            continue
        obs = [o for o in r.json()["observations"] if o["value"] != "."]
        print(f"[O] {name}｜{len(obs)} 筆｜{obs[0]['date']} ～ {obs[-1]['date']}｜最新值 {obs[-1]['value']}")
    except Exception as e:
        print(f"[X] {name}｜{type(e).__name__}: {str(e)[:100]}")
