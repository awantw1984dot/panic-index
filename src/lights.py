# -*- coding: utf-8 -*-
"""
冰水燈：非常態投資學（投資音）課程的「市場氛圍儀表板」
- 和特賣會分數並列：分數看「溫度」，燈號看「左側非常態的訊號亮了幾格」
- 亮 1～2 格：提高警覺；亮 3 格以上：冰水區（課程 3-1：「亮一格提高警覺，亮三格四格才是非常態的強烈訊號」）
- 之後各章節的新條件請加在 CFG，並在註解標明章節

門檻口徑說明
- 融資維持率：本專案自算（上市個股融資市值 ÷ 融資金額），2025/4 實測比課程數字高約 4 個百分點，
  所以課程 140% 換算成 144%，130% 換算成 134%
"""
import json
import os

import numpy as np
import pandas as pd

from common import DATA, load_csv

CFG = {
    # 1 定位（水溫）— 課程 3-1：短中長三條均線（十日、十週、十月）全部下彎，價格跌破長期均線
    "ma_short": 10, "ma_mid": 50, "ma_long": 200,      # 以交易日近似：10 日、10 週≈50 日、10 月≈200 日
    "slope_lag": 5,                                     # 下彎＝均線低於 5 個交易日前
    # 2 位置（深度）— 課程 3-1：加權接近或跌破 5 年線；權值 100 大有 3～4 成落入長期均線之下
    # 課程說 3～4 成，但 2024～2026 台股漲勢集中在少數權值股，35% 幾乎是常態（中位數約 40%），回測後改 60%
    "ma_5y": 1250, "near_5y": 1.05, "top_n": 100, "top_below_pct": 60,
    "tpex_ma": 240,                                     # 櫃買跌破年線：課程說會領先加權，只當參考不計燈
    # 3 壓力 — 課程 2-3／3-1：融資維持率 140% 開始布局、130% 強力（本專案口徑 +4）
    "maint_lamp": 144,
    # 4 情緒 — 課程 3-1：無上漲類股（一個月 3 次可開始分批、5 次極度恐慌）、VIX 40 第一批、跌停家數極端
    "noup_window": 22, "noup_days": 3, "vix_lamp": 40, "limit_down_lamp": 200,
    # 5 外部 — 課程 3-1：費半、S&P500、Nasdaq 同步走弱；國安基金宣布進場
    "fund_days": 60,                                    # 國安基金宣布後 60 個交易日內維持亮燈
    # 型態 — 課程 3-1：黑天鵝（急殺，考驗信心）vs 灰犀牛（緩跌，VIX 多在 35 以下，考驗耐心）
    "swan_vix": 40, "swan_jump": 30, "swan_limit_down": 300, "rhino_vix": 35,
    # 三角分批（大盤 ETF 20／30／50）— 課程 3-3 範例條件；作者未給機械公式，只做「人工檢視」提示
    # 以下為使用者定規（2026/11，非作者原文）：同一批範例條件達 tri_need 項就提示；短期跌幅＝距一年高點
    "ma_2y": 500, "dd_window": 250, "tri_need": 2, "tri_pending_days": 20,
    "b1_vix": 40, "b1_dd": 30,                         # 第一批：VIX 升破 40、亮 1～2 格、跌破兩年線／跌幅 >30%
    "b2_vix": 45, "b2_maint": 144, "b2_dd": 40,        # 第二批：VIX >45、融資 <140%（本專案 144）、觀察類股持續缺席、五年線／跌幅 40%
    "b3_vix": 50, "b3_maint": 139, "b3_lamps": 4,      # 第三批：五格幾乎全亮、融資 <約 135%（本專案 139）、VIX >50、國安基金、三循環集中
}
TRI = [("第一批", 20), ("第二批", 30), ("第三批", 50)]
NAMES = ["定位", "位置", "壓力", "情緒", "外部"]


def levels(n):
    return "冰水區" if n >= 3 else "警覺" if n >= 1 else "常態"


def _slope_down(ma, lag):
    return ma < ma.shift(lag)


def top100_below(closes, shares, c=CFG):
    """每天依市值（收盤價 × 目前已發行股數）取前 100 大，計算收盤價低於 10 月線的比例"""
    if closes.empty or shares.empty:
        return pd.Series(dtype=float)
    codes = [k for k in closes.columns if k in shares.index]
    px = closes[codes]
    ma = px.rolling(c["ma_long"], min_periods=c["ma_long"]).mean()
    mcap = px * shares.loc[codes].values
    top = mcap.rank(axis=1, ascending=False) <= c["top_n"]
    valid = top & ma.notna() & px.notna()
    below = (px < ma) & valid
    n = valid.sum(axis=1)
    return (below.sum(axis=1) / n.replace(0, np.nan) * 100).where(n >= c["top_n"] * 0.8)


def fund_dates():
    """manual_events.json 裡 type 為「國安基金」的日期"""
    p = os.path.join(DATA, "manual_events.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        ev = json.load(f)
    return sorted(pd.Timestamp(e["date"]) for e in ev if e.get("type") == "國安基金")


def compute(tw, us, tw_score, c=CFG):
    """tw：tw_daily（已清理）；us：us_daily；tw_score：台股分數。回傳以台股交易日為索引的燈號表"""
    idx = tw.index
    out = pd.DataFrame(index=idx)

    # 加權指數：長歷史（2018 起）＋日資料
    long = load_csv("taiex_long.csv")
    taiex = tw["TAIEX"]
    if not long.empty and "TAIEX" in long:
        taiex = taiex.combine_first(long["TAIEX"]).sort_index()

    # 1 定位
    mas = {k: taiex.rolling(c[k], min_periods=c[k]).mean() for k in ["ma_short", "ma_mid", "ma_long"]}
    down = pd.concat([_slope_down(m, c["slope_lag"]) for m in mas.values()], axis=1).all(axis=1)
    has = pd.concat(list(mas.values()), axis=1).notna().all(axis=1)
    l1 = (down & (taiex < mas["ma_long"])).where(has)
    out["定位"] = l1.reindex(idx)
    out["d_ma_down"] = pd.concat([_slope_down(m, c["slope_lag"]).astype(int) for m in mas.values()], axis=1).sum(axis=1).where(has).reindex(idx)
    out["d_vs_ma200"] = ((taiex / mas["ma_long"] - 1) * 100).reindex(idx)

    # 2 位置
    ma5y = taiex.rolling(c["ma_5y"], min_periods=c["ma_5y"]).mean()
    dist5y = (taiex / ma5y - 1) * 100
    closes_p = os.path.join(DATA, "tw_closes.csv.gz")
    closes = pd.read_csv(closes_p, index_col=0, parse_dates=True) if os.path.exists(closes_p) else pd.DataFrame()
    shares = load_csv_code("tw_shares.csv")
    top = top100_below(closes, shares, c).reindex(idx)
    near = (taiex <= ma5y * c["near_5y"]).where(ma5y.notna()).reindex(idx)
    topl = (top >= c["top_below_pct"]).where(top.notna())
    out["位置"] = _any(near, topl)
    out["d_5y"] = dist5y.reindex(idx)
    out["d_top_below"] = top
    tpex = us["TPEX"].dropna() if "TPEX" in us else pd.Series(dtype=float)
    if len(tpex):
        tma = tpex.rolling(c["tpex_ma"], min_periods=c["tpex_ma"]).mean()
        tdist = ((tpex / tma - 1) * 100).dropna()
        out["d_tpex_vs_ma240"] = tdist.reindex(idx, method="ffill", tolerance=pd.Timedelta(days=5)) if len(tdist) else np.nan
    else:
        out["d_tpex_vs_ma240"] = np.nan

    # 3 壓力
    m = tw["margin_maint"]
    out["壓力"] = (m <= c["maint_lamp"]).where(m.notna())
    out["d_maint"] = m

    # 4 情緒
    vix = us["VIX"].dropna() if "VIX" in us else pd.Series(dtype=float)
    vix_tw = vix.reindex(idx, method="ffill", tolerance=pd.Timedelta(days=5)) if len(vix) else pd.Series(np.nan, index=idx)
    noup = pd.Series(np.nan, index=idx)
    if "sector_up" in tw:
        z = (tw["sector_up"] == 0).astype(float).where(tw["sector_up"].notna())
        noup = z.rolling(c["noup_window"], min_periods=1).sum().where(z.rolling(c["noup_window"], min_periods=1).count() >= c["noup_window"] * 0.8)
    ld = tw["limit_down"] if "limit_down" in tw else pd.Series(np.nan, index=idx)
    out["情緒"] = _any((noup >= c["noup_days"]).where(noup.notna()),
                       (vix_tw >= c["vix_lamp"]).where(vix_tw.notna()),
                       (ld >= c["limit_down_lamp"]).where(ld.notna()))
    out["d_noup"] = noup
    out["d_vix"] = vix_tw
    out["d_limit_down"] = ld

    # 5 外部
    ext = []
    for col in ["SOX", "SPX", "NASDAQ"]:
        if col in us and us[col].notna().sum() >= c["ma_long"]:
            s = us[col].dropna()
            b = (s < s.rolling(c["ma_long"], min_periods=c["ma_long"]).mean()).where(s.rolling(c["ma_long"]).mean().notna())
            ext.append(b.astype(float).reindex(idx, method="ffill", tolerance=pd.Timedelta(days=5)).rename(col))
    if ext:
        e = pd.concat(ext, axis=1)
        out["d_ext_below"] = e.sum(axis=1).where(e.notna().any(axis=1))
        out["d_ext_n"] = e.notna().sum(axis=1)
        allb = (e.sum(axis=1) == len(ext)).where(e.notna().all(axis=1))
    else:
        out["d_ext_below"] = out["d_ext_n"] = np.nan
        allb = pd.Series(np.nan, index=idx)
    fund = pd.Series(False, index=idx)
    for d in fund_dates():
        pos = idx.searchsorted(d)
        fund.iloc[pos:pos + c["fund_days"]] = True
    out["d_fund"] = fund
    out["外部"] = _any(allb, fund.where(fund))   # 國安基金只會讓燈「亮」，沒宣布不代表「不亮」

    # 統計與型態
    lamps = out[NAMES]
    out["亮燈數"] = (lamps == True).sum(axis=1)
    out["燈號"] = out["亮燈數"].map(levels)
    vmax = vix_tw.rolling(10, min_periods=1).max()
    jump = tw_score.reindex(idx) - tw_score.reindex(idx).rolling(10, min_periods=1).min()
    ldmax = ld.rolling(10, min_periods=1).max()
    swan = (vmax >= c["swan_vix"]) | (jump >= c["swan_jump"]) | (ldmax >= c["swan_limit_down"])
    rhino = (out["定位"] == True) & (vmax < c["rhino_vix"])
    active = out["亮燈數"] >= 1   # 型態只描述左側非常態，沒亮燈就不判斷
    out["型態"] = np.where(active & swan, "急殺型（黑天鵝）", np.where(active & rhino, "緩跌型（灰犀牛）", None))

    # 三角分批（課程 3-3）：每批列出範例條件是否成立，達 tri_need 項提示「可人工檢視」
    ma2y = taiex.rolling(c["ma_2y"], min_periods=c["ma_2y"]).mean()
    hi = taiex.rolling(c["dd_window"], min_periods=int(c["dd_window"] * 0.8)).max()
    dd = ((1 - taiex / hi) * 100).reindex(idx)
    b2y = (taiex < ma2y).where(ma2y.notna()).reindex(idx)
    b5y = (taiex < ma5y).where(ma5y.notna()).reindex(idx)
    vt = vix_tw
    conds = {
        1: {"VIX≥40": (vt >= c["b1_vix"]).where(vt.notna()), "冰水燈亮≥1格": out["亮燈數"] >= 1,
            "跌破2年線": b2y, "距一年高點跌≥30%": (dd >= c["b1_dd"]).where(dd.notna())},
        2: {"VIX≥45": (vt >= c["b2_vix"]).where(vt.notna()), "融資維持率≤144%": (m <= c["b2_maint"]).where(m.notna()),
            "無上漲類股持續": (noup >= c["noup_days"]).where(noup.notna()),
            "跌破5年線或跌幅≥40%": _any(b5y, (dd >= c["b2_dd"]).where(dd.notna()))},
        3: {"亮燈≥4格": out["亮燈數"] >= c["b3_lamps"], "融資維持率≤139%": (m <= c["b3_maint"]).where(m.notna()),
            "VIX≥50": (vt >= c["b3_vix"]).where(vt.notna()), "國安基金進場": fund, "三循環集中": out["定位"]},
    }
    reach = pd.Series(0, index=idx)
    for k, cd in conds.items():
        df = pd.concat(cd, axis=1)
        for name in cd:
            out[f"t{k}_{name}"] = df[name]
        hit = (df == True).sum(axis=1)
        out[f"t{k}_n"] = hit
        reach = reach.where(~((hit >= c["tri_need"]) & active), k)
    out["t_reach"] = reach.where(active, 0)
    # 本輪：亮燈 ≥1 的連續期間；記錄本輪最高到第幾批，回到常態後保留「待決」提示 tri_pending_days 天
    ep = (active & ~active.shift(1, fill_value=False)).cumsum().where(active)
    out["t_ep_start"] = pd.Series(idx, index=idx).where(active).groupby(ep).transform("min")
    out["t_ep_max"] = out["t_reach"].where(active).groupby(ep).cummax()
    last_max = out["t_ep_max"].ffill()
    since = (~active).astype(int).groupby(active.cumsum()).cumsum()
    out["t_pending"] = (~active & last_max.between(1, 2) & (since <= c["tri_pending_days"])).astype(bool)
    out["t_pending_max"] = last_max.where(out["t_pending"])
    return out


def _any(*series):
    """任一條件成立就亮；全部沒資料才算無資料"""
    df = pd.concat(series, axis=1)
    lit = (df == True).any(axis=1)
    return lit.where(df.notna().any(axis=1) | lit)


def load_csv_code(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return pd.Series(dtype=float)
    return pd.read_csv(p, index_col=0, dtype={"code": str})["shares"]


def _f(v, d=1):
    return None if v is None or pd.isna(v) else round(float(v), d)


def row_json(L, d):
    """給網頁的單日燈號：亮燈（True／False／None＝無資料）、說明數字、型態"""
    r = L.loc[d]
    lamp = {k: (None if pd.isna(r[k]) else bool(r[k])) for k in NAMES}
    return {"lamps": lamp, "n": int(r["亮燈數"]), "level": r["燈號"], "type": r["型態"] if isinstance(r["型態"], str) else None,
            "d": {"ma_down": _f(r["d_ma_down"], 0), "vs_ma200": _f(r["d_vs_ma200"]), "vs_5y": _f(r["d_5y"]),
                  "top_below": _f(r["d_top_below"], 0), "tpex_vs_ma240": _f(r["d_tpex_vs_ma240"]),
                  "maint": _f(r["d_maint"]), "noup": _f(r["d_noup"], 0), "vix": _f(r["d_vix"]),
                  "limit_down": _f(r["d_limit_down"], 0), "ext_below": _f(r["d_ext_below"], 0),
                  "ext_n": _f(r["d_ext_n"], 0), "fund": bool(r["d_fund"])},
            "tri": tri_json(L, d)}


def tri_json(L, d):
    """三角分批：每批條件（True／False／None＝無資料）、今天可檢視到第幾批、本輪最高、回到常態後的待決狀態"""
    r = L.loc[d]
    if "t_reach" not in L:
        return None
    batches = []
    for k, (name, pct) in enumerate(TRI, 1):
        cs = {c[len(f"t{k}_"):]: (None if pd.isna(r[c]) else bool(r[c]))
              for c in L.columns if c.startswith(f"t{k}_") and c != f"t{k}_n"}
        batches.append({"name": name, "pct": pct, "n": int(r[f"t{k}_n"]), "of": len(cs), "conds": cs})
    st = r["t_ep_start"]
    return {"batches": batches, "reach": int(r["t_reach"]),
            "ep_max": None if pd.isna(r["t_ep_max"]) else int(r["t_ep_max"]),
            "ep_start": None if pd.isna(st) else pd.Timestamp(st).strftime("%Y-%m-%d"),
            "pending": bool(r["t_pending"]), "pending_max": None if pd.isna(r["t_pending_max"]) else int(r["t_pending_max"]),
            "need": CFG["tri_need"]}
