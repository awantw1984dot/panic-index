# -*- coding: utf-8 -*-
"""P0-0 回歸測試：台股退潮通知與資料停更通知

背景：commit a94a502 新增停更通知時，誤把台股退潮的判斷式取代掉，
造成「停更時發出台股買入通知、真正退潮時不通知」。本檔防止同樣錯誤再次出現。

做法：用合成的 score_tw / score_us 輸出取代真實計算，只執行 score.main() 的通知區塊；
所有檔案寫在暫存目錄，不連網、不碰正式 data/、docs/。
執行：python -m pytest tests/test_notify_p00.py（或 python tests/test_notify_p00.py）
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile

import pandas as pd

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
BUY = "台股可以進場搶購"
N = 30


def _today():
    return pd.Timestamp.now(tz="Asia/Taipei").tz_localize(None).normalize()


def _frame(exits, recent_col, lag=0):
    """合成一個市場的計分輸出；lag = 最後一筆距今幾個營業日（模擬停更）"""
    end = _today() - pd.tseries.offsets.BDay(lag if lag else 1)
    idx = pd.bdate_range(end=end, periods=N)
    sc = pd.Series([50.0] * N, index=idx)
    out = pd.DataFrame({"score": sc, "組_A": sc, "指標_X": sc, "訊號_C1": True,
                        recent_col: True, "退潮": pd.Series(exits, index=idx).astype(bool)})
    return out, pd.DataFrame({"VAL": sc}, index=idx)


def _tw(exit_last=False, exit_prev=False, lag=0):
    return _frame([False] * (N - 2) + [exit_prev, exit_last], "近期恐慌", lag)


def _us(lag=0):
    return _frame([False] * N, "近期真恐慌", lag)


def _prev(**kw):
    p = {"tw_zone": "原價", "us_zone": "原價", "quadrant": "正常環境", "tw_exit": False,
         "us_exit": False, "stale": [], "tw_heat_date": None, "us_heat_date": None}
    p.update(kw)
    return p


def _run(prev, tw, us, runs=1):
    """在暫存目錄執行 score.main()，回傳每次產生的 status.json 的 events"""
    root = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(root, "data"))
        os.makedirs(os.path.join(root, "docs"))
        with open(os.path.join(root, "docs", "status.json"), "w", encoding="utf-8") as f:
            json.dump(prev, f, ensure_ascii=False)
        old_env = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = os.path.join(root, "data")
        sys.path.insert(0, SRC)
        for m in ("common", "score"):
            sys.modules.pop(m, None)
        spec = importlib.util.spec_from_file_location("score", os.path.join(SRC, "score.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.path.remove(SRC)
        if old_env is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = old_env
        mod.ROOT, mod.DATA = root, os.path.join(root, "data")
        mod.score_tw = lambda _df: tw
        mod.score_us = lambda _df: us
        mod.load_csv = lambda _name: pd.DataFrame()
        events = []
        for _ in range(runs):
            with contextlib.redirect_stdout(io.StringIO()):
                mod.main()
            with open(os.path.join(root, "docs", "status.json"), encoding="utf-8") as f:
                events.append(json.load(f)["events"])
        return events
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_t02_exit_false_to_true_notifies_once():
    ev = _run(_prev(tw_exit=False), _tw(exit_last=True), _us())[0]
    assert ev.count(BUY) == 1


def test_t04_tw_stale_without_exit_no_buy():
    ev = _run(_prev(), _tw(exit_last=False, lag=6), _us())[0]
    assert any(e.startswith("資料停更") for e in ev)
    assert BUY not in ev


def test_t05b_only_us_stale_no_tw_buy():
    ev = _run(_prev(), _tw(exit_last=False), _us(lag=8))[0]
    assert any(e.startswith("資料停更") for e in ev)
    assert BUY not in ev


def test_t10_same_exit_data_twice_no_duplicate():
    first, second = _run(_prev(tw_exit=False), _tw(exit_last=True), _us(), runs=2)
    assert first.count(BUY) == 1
    assert BUY not in second


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
