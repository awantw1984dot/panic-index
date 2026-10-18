# -*- coding: utf-8 -*-
"""共用工具：HTTP 請求、CSV 合併、日期轉換"""
import datetime as dt
import os
import time

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("DATA_DIR") or os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)
START = dt.date.fromisoformat(os.environ.get("START_DATE", "2023-10-01"))   # 只保留近 3 年
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def get(url, method="GET", retries=4, wait=2.2, timeout=40, **kw):
    """帶重試的請求；每次請求後固定等待，避免被證交所封鎖"""
    last = None
    for i in range(retries):
        try:
            r = requests.request(method, url, headers=UA, timeout=timeout, **kw)
            time.sleep(wait)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(wait)
        time.sleep(15 * (i + 1))
    raise RuntimeError(f"請求失敗 {url}：{last}")


def roc_to_date(s):
    """'115/07/01' → date(2026,7,1)"""
    y, m, d = s.strip().split("/")
    return dt.date(int(y) + 1911, int(m), int(d))


def num(s):
    """'1,234' → 1234.0；無法轉換回傳 None"""
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def load_csv(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return pd.DataFrame()
    return pd.read_csv(p, index_col=0, parse_dates=True)


def save_merge(name, new):
    """與既有資料合併：新值覆蓋舊值，舊資料保留（讓 FRED 等歷史越存越長）"""
    old = load_csv(name)
    if not old.empty:
        new = new.combine_first(old) if new is not None and not new.empty else old
        for c in old.columns:
            if c not in new.columns:
                new[c] = old[c]
    new = new.sort_index()
    new.index.name = "date"
    new.to_csv(os.path.join(DATA, name), float_format="%.6g")
    return new
