# -*- coding: utf-8 -*-
"""美股資料：yfinance（VIX、VIX3M、MOVE、JNK、IEF、S&P500、費半）＋ FRED（HY/IG 利差、STLFSI）"""
import json
import os
import sys
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from common import DATA, START, get, save_merge

YF = {"^VIX": "VIX", "^VIX3M": "VIX3M", "^MOVE": "MOVE", "JNK": "JNK", "IEF": "IEF",
      "^GSPC": "SPX", "^SOX": "SOX"}
FRED = {"BAMLH0A0HYM2": "HY_OAS", "BAMLC0A0CM": "IG_OAS", "STLFSI4": "STLFSI"}
ICE = ["HY_OAS", "IG_OAS"]   # ICE BofA 授權：不得公開發布原始數值


def fetch_yf():
    df = yf.download(list(YF), start=str(START), auto_adjust=True, progress=False)["Close"]
    df = df.rename(columns=YF)
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df


def fetch_cboe(name):
    """CBOE 官方 CSV（VIX、VIX3M 備援來源）"""
    import io
    r = get(f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv", wait=0.5)
    d = pd.read_csv(io.StringIO(r.text))
    d.index = pd.to_datetime(d.iloc[:, 0], format="%m/%d/%Y")
    return d["CLOSE"].rename(name)[lambda x: x.index >= pd.Timestamp(START)]


def fill_from_cboe(df):
    """yfinance 缺值或落後時，用 CBOE 補上（容錯）"""
    for col in ["VIX", "VIX3M"]:
        try:
            last_all = df.dropna(how="all").index.max()
            last_col = df[col].dropna().index.max() if col in df and df[col].notna().any() else None
            if last_col is None or last_col < last_all or df[col].isna().mean() > 0.02:
                c = fetch_cboe(col)
                df[col] = df[col].combine_first(c) if col in df else c
                print(f"  {col} 以 CBOE 補值（yfinance 不完整）")
        except Exception as e:
            print(f"  {col} CBOE 備援失敗：{e}")
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


def unclosed_from(now=None):
    """美股尚未收盤（美東 16:30 前）時，回傳當天日期；之後的列都是盤中價，不可使用"""
    et = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    return pd.Timestamp(et.date()) if et.time() < dt.time(16, 30) else None


def drop_unclosed(df, now=None):
    """移除美股當天未收盤的盤中資料（台北晚上更新時美股正在交易）；隔天早上收盤後再收進來"""
    cut = unclosed_from(now)
    if cut is None or df.empty:
        return df
    return df[df.index < cut]


def main():
    key = os.environ.get("FRED_API_KEY")
    if not key:
        sys.exit("缺少 FRED_API_KEY")
    try:
        a = fetch_yf()
    except Exception as e:
        print(f"  yfinance 失敗：{e}")
        a = pd.DataFrame()
    a = drop_unclosed(fill_from_cboe(a))
    b = fetch_fred(key)
    # ICE 利差（HY、IG）依授權僅供內部使用：另存 data/fred_ice.csv（不提交到公開 repo），不寫進 us_daily.csv
    ice = b[[c for c in ICE if c in b]]
    ice.index.name = "date"
    ice.to_csv(os.path.join(DATA, "fred_ice.csv"), float_format="%.6g")
    df = a.join(b.drop(columns=ICE, errors="ignore"), how="outer")
    df = df.dropna(how="all")
    df = save_merge("us_daily.csv", df)
    clean = drop_unclosed(df.drop(columns=ICE, errors="ignore"))   # 移除舊檔殘留的 ICE 欄位與盤中列
    if len(clean) != len(df) or any(c in df for c in ICE):
        df = clean
        df.to_csv(os.path.join(DATA, "us_daily.csv"), float_format="%.6g")
    print(f"美股資料：{len(df)} 列，{df.index.min().date()} ～ {df.index.max().date()}")
    print("各欄最新值：")
    print(df.ffill().iloc[-1].round(3).to_string())
    print("缺值數：", df.isna().sum().to_dict())
    fetch_events(key)


if __name__ == "__main__":
    main()
