# -*- coding: utf-8 -*-
"""美股盤中資料不得進入計分：台北晚上更新時美股尚未收盤，當天的列要排除"""
import datetime as dt
import os
import sys
import types

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.modules.setdefault("yfinance", types.ModuleType("yfinance"))
import fetch_us as F  # noqa: E402

UTC = dt.timezone.utc
df = pd.DataFrame({"VIX": [18.4, 17.7]}, index=pd.to_datetime(["2026-10-19", "2026-10-20"]))


def test_taipei_evening_drops_today():      # 台北 22:52 = 美東 10:52（盤中）
    out = F.drop_unclosed(df, dt.datetime(2026, 10, 20, 14, 52, tzinfo=UTC))
    assert list(out.index.strftime("%Y-%m-%d")) == ["2026-10-19"]


def test_taipei_morning_keeps_close():      # 台北隔日 07:30 = 美東 19:30（已收盤）
    out = F.drop_unclosed(df, dt.datetime(2026, 10, 20, 23, 30, tzinfo=UTC))
    assert len(out) == 2


def test_before_close_boundary():           # 美東 16:29 排除、16:30 保留
    assert len(F.drop_unclosed(df, dt.datetime(2026, 10, 20, 20, 29, tzinfo=UTC))) == 1
    assert len(F.drop_unclosed(df, dt.datetime(2026, 10, 20, 20, 30, tzinfo=UTC))) == 2


def test_winter_time():                     # 冬令：台北 21:30 = 美東 08:30（開盤前），當天尚無資料也不受影響
    w = pd.DataFrame({"VIX": [18.0]}, index=pd.to_datetime(["2026-11-09"]))
    assert len(F.drop_unclosed(w, dt.datetime(2026, 11, 10, 13, 30, tzinfo=UTC))) == 1


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print("PASS", k)
