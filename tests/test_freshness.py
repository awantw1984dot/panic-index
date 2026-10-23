# -*- coding: utf-8 -*-
"""資料時間確認：依交易所行事曆判斷「此刻應該已有」的最新交易日，落後就提醒"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_data"))
import score as S  # noqa: E402

T = lambda s: pd.Timestamp(s, tz="Asia/Taipei").tz_convert("UTC")
D = lambda s: pd.Timestamp(s)


def test_friday_morning_before_us_update():      # 週五 08:18：台股應有週四、美股應有週四收盤
    assert S.expected_dates(T("2026-10-23 08:18")) == (D("2026-10-22"), D("2026-10-22"))


def test_evening_while_us_trading():              # 週五凌晨 02:10（美東週四 14:10 盤中）：美股只應有週三
    assert S.expected_dates(T("2026-10-23 02:10")) == (D("2026-10-22"), D("2026-10-21"))


def test_tw_before_and_after_2100():
    assert S.expected_dates(T("2026-10-22 20:59"))[0] == D("2026-10-21")
    assert S.expected_dates(T("2026-10-22 21:00"))[0] == D("2026-10-22")


def test_weekend_and_tw_holiday():
    assert S.expected_dates(T("2026-10-24 10:00")) == (D("2026-10-23"), D("2026-10-23"))
    assert S.expected_dates(T("2026-10-09 22:00"))[0] == D("2026-10-08")   # 國慶補假 10/9 休市


def test_freshness_messages():
    now = T("2026-10-23 08:18")
    assert S.freshness("2026-10-22", "2026-10-22", now) == []
    msg = S.freshness("2026-10-22", "2026-10-21", now)
    assert msg == ["美股缺 10/22 收盤資料（停在 10/21）"]
    assert S.freshness("2026-10-21", "2026-10-22", now) == ["台股缺 10/22 資料（停在 10/21）"]


def test_next_due():
    assert S.next_due(T("2026-10-23 08:24")) == "202610232243"   # 週五早上 → 當晚 21:43 + 60 分
    assert S.next_due(T("2026-10-23 21:50")) == "202610240843"   # 週五晚上 → 週六 07:43 + 60 分
    assert S.next_due(T("2026-10-24 08:00")) == "202610262243"   # 週六早上 → 週一 21:43 + 60 分
    assert S.next_due(T("2026-10-27 02:10")) == "202610270843"   # 晚上那次延遲到凌晨 → 當天 07:43 + 60 分


if __name__ == "__main__":
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            f(); print("PASS", k)
