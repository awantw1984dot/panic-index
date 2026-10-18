# -*- coding: utf-8 -*-
"""美股資料：yfinance（VIX、VIX3M、MOVE、JNK、IEF、S&P500、費半）＋ FRED（HY/IG 利差、STLFSI）"""
import os
import sys

import pandas as pd
import yfinance as yf

from common import START, get, save_merge

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


if __name__ == "__main__":
    main()
