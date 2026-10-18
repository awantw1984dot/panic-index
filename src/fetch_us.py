# -*- coding: utf-8 -*-
"""美股資料：yfinance（VIX、VIX3M、MOVE、JNK、IEF、S&P500、費半）＋ FRED（HY/IG 利差、STLFSI）"""
import json
import os
import sys
import datetime as dt

import pandas as pd
import yfinance as yf

from common import DATA, START, get, save_merge

YF = {"^VIX": "VIX", "^VIX3M": "VIX3M", "^MOVE": "MOVE", "JNK": "JNK", "IEF": "IEF",
      "^GSPC": "SPX", "^SOX": "SOX"}
FRED = {"BAMLH0A0HYM2": "HY_OAS", "BAMLC0A0CM": "IG_OAS", "STLFSI4": "STLFSI"}


def fetch_yf():
    df = yf.download(list(YF), start=str(START), auto_adjust=True, progress=False)["Close"]
    df = df.rename(columns=YF)
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df


def fetch_fred(key):
    out = {}
    for sid, col in FRED.items():
        r = get("https://api.stlouisfed.org/fred/series/observations", wait=0.5,
                params={"series_id": sid, "api_key": key, "file_type": "json",
                        "observation_start": str(START)})
        obs = [(o["date"], float(o["value"])) for o in r.json()["observations"] if o["value"] != "."]
        out[col] = pd.Series(dict(obs), dtype=float)
    df = pd.DataFrame(out)
    df.index = pd.to_datetime(df.index)
    return df


# FRED 的公布日程（release_id）：CPI、PPI、非農就業
RELEASES = {10: "CPI", 46: "PPI", 50: "非農就業"}
# FOMC 利率決策（美東時間會議第二天公布；台灣時間為隔天凌晨）。2027 為聯準會暫定日程
FOMC = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16",
        "2026-10-28", "2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
        "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08"]


def fetch_events(key):
    today = dt.date.today()
    out = [{"date": d, "name": "FOMC 利率決策"} for d in FOMC if d >= str(today - dt.timedelta(days=7))]
    for rid, name in RELEASES.items():
        try:
            r = get("https://api.stlouisfed.org/fred/release/dates", wait=0.5,
                    params={"release_id": rid, "api_key": key, "file_type": "json",
                            "realtime_start": str(today - dt.timedelta(days=7)), "realtime_end": "9999-12-31",
                            "include_release_dates_with_no_data": "true", "sort_order": "asc", "limit": 20})
            for x in r.json().get("release_dates", []):
                out.append({"date": x["date"], "name": name})
        except Exception as e:
            print(f"  {name} 公布日抓取失敗：{e}")
    out = sorted({(e["date"], e["name"]): e for e in out}.values(), key=lambda e: e["date"])
    with open(os.path.join(DATA, "events.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("近期事件：", [f"{e['date']} {e['name']}" for e in out if e["date"] <= str(today + dt.timedelta(days=21))])


def main():
    key = os.environ.get("FRED_API_KEY")
    if not key:
        sys.exit("缺少 FRED_API_KEY")
    a, b = fetch_yf(), fetch_fred(key)
    df = a.join(b, how="outer")
    df = df.dropna(how="all")
    df = save_merge("us_daily.csv", df)
    print(f"美股資料：{len(df)} 列，{df.index.min().date()} ～ {df.index.max().date()}")
    print("各欄最新值：")
    print(df.ffill().iloc[-1].round(3).to_string())
    print("缺值數：", df.isna().sum().to_dict())
    fetch_events(key)


if __name__ == "__main__":
    main()
