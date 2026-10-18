# -*- coding: utf-8 -*-
"""
計算特賣會儀表板分數
- 各指標轉成滾動百分位（只用當天以前的資料，避免偷看未來）
- 美股、台股分開加權成 0~100 分
- 四格狀態、退潮訊號
輸出：data/scores_us.csv、data/scores_tw.csv、site/data.json
"""
import json
import os

import numpy as np
import pandas as pd

from common import DATA, ROOT, load_csv

WIN, MINP = 504, 252          # 百分位視窗約 2 年，至少 1 年資料才給分
PANIC = 60                    # 四格判斷：≥60 視為恐慌側
ZONES = [(0, 20, "漲價中"), (20, 60, "原價"), (60, 80, "開始打折"), (80, 101, "特賣會")]

US_GROUPS = {   # 組別: (權重, [指標])
    "信用": (0.40, ["HY利差", "IG利差", "JNK/IEF回撤"]),
    "股市波動": (0.35, ["VIX", "VIX期限結構"]),
    "債市波動": (0.25, ["MOVE"]),
}
TW_GROUPS = {
    "融資": (0.30, ["融資維持率(反向)", "融資10日變化(反向)"]),
    "臺指VIX": (0.25, ["臺指VIX"]),
    "外資期貨": (0.20, ["外資期貨淨空單10日變化"]),
    "市場寬度": (0.25, ["跌破季線比例"]),
}


def pct_rank(s):
    """當天數值在過去 WIN 天（含當天）中的百分位 0~100"""
    s = s.dropna()
    return s.rolling(WIN, min_periods=MINP).apply(
        lambda x: (x[:-1] < x[-1]).mean() * 100 + (x[:-1] == x[-1]).mean() * 50, raw=True)


def zone(x):
    if pd.isna(x):
        return None
    for lo, hi, name in ZONES:
        if lo <= x < hi:
            return name


def weighted(comp, groups):
    g = pd.DataFrame({k: comp[[c for c in cols if c in comp]].mean(axis=1) for k, (_, cols) in groups.items()})
    w = pd.Series({k: v[0] for k, v in groups.items()})
    avail = g.notna()
    score = (g.fillna(0) * w).sum(axis=1) / (avail * w).sum(axis=1)
    score[avail.sum(axis=1) == 0] = np.nan
    return score, g


# ---------------- 美股 ----------------
def score_us(us):
    us = us.copy()
    trade = us["VIX"].notna()
    us[["HY_OAS", "IG_OAS", "STLFSI"]] = us[["HY_OAS", "IG_OAS", "STLFSI"]].ffill(limit=10)
    us = us[trade]
    ratio = us["JNK"] / us["IEF"]
    term = us["VIX"] / us["VIX3M"]
    c = pd.DataFrame(index=us.index)
    c["HY利差"] = pct_rank(us["HY_OAS"])
    c["IG利差"] = pct_rank(us["IG_OAS"])
    c["JNK/IEF回撤"] = pct_rank(1 - ratio / ratio.rolling(252, min_periods=60).max())
    c["VIX"] = pct_rank(us["VIX"])
    c["VIX期限結構"] = pct_rank(term)
    c["MOVE"] = pct_rank(us["MOVE"])
    score, g = weighted(c, US_GROUPS)

    # 退潮訊號：近 20 天曾「真恐慌」→ 期限結構回正 ＋ 利差收斂
    true_panic = (score >= 80) & (term >= 1) & (us["VIX"] >= 20)
    recent = true_panic.astype(float).rolling(20, min_periods=1).max() == 1
    checks = pd.DataFrame({
        "期限結構回正": term < 1,
        "信用利差收斂": us["HY_OAS"].diff(10) < 0,
    })
    out = pd.concat([score.rename("score"), g.add_prefix("組_"), c.add_prefix("指標_"), checks.add_prefix("訊號_")], axis=1)
    out["近期真恐慌"] = recent
    out["退潮"] = recent & checks.all(axis=1)
    raw = us[["VIX", "VIX3M", "MOVE", "HY_OAS", "IG_OAS", "STLFSI", "SPX", "SOX"]].copy()
    raw["VIX期限結構"] = term
    raw["JNK/IEF"] = ratio
    return out, raw


# ---------------- 台股 ----------------
def score_tw(tw):
    tw = tw[tw["TAIEX"].notna()].copy()
    c = pd.DataFrame(index=tw.index)
    c["融資維持率(反向)"] = 100 - pct_rank(tw["margin_maint"])
    c["融資10日變化(反向)"] = 100 - pct_rank(tw["margin_amt_k"].pct_change(10))
    c["臺指VIX"] = pct_rank(tw["tvix"])
    c["外資期貨淨空單10日變化"] = 100 - pct_rank(tw["fut_foreign_net_oi"].diff(10))
    c["跌破季線比例"] = pct_rank(tw["below_ma60_pct"])
    score, g = weighted(c, TW_GROUPS)

    # 退潮訊號（近 20 天分數曾 ≥ 60 才檢查）
    recent = (score >= PANIC).astype(float).rolling(20, min_periods=1).max() == 1
    m, b, v = tw["margin_maint"], tw["below_ma60_pct"], tw["tvix"]
    checks = pd.DataFrame({
        "融資維持率止跌回升": (m.diff(3) > 0) & (m > m.rolling(10).min() * 1.01),
        "市場寬度改善": b.diff(5) < 0,
        "臺指VIX回落": (v.diff(5) < 0) & (v < v.rolling(10).max() * 0.9),
    })
    out = pd.concat([score.rename("score"), g.add_prefix("組_"), c.add_prefix("指標_"), checks.add_prefix("訊號_")], axis=1)
    out["近期恐慌"] = recent
    out["退潮"] = recent & checks.all(axis=1)
    raw = tw[["TAIEX", "margin_maint", "margin_amt_k", "tvix", "fut_foreign_net_oi", "below_ma60_pct", "adv", "dec"]]
    return out, raw


def quadrant(tw_s, us_s):
    if pd.isna(tw_s) or pd.isna(us_s):
        return None
    t, u = tw_s >= PANIC, us_s >= PANIC
    return "系統性恐慌" if t and u else "本土事件" if t else "預警" if u else "正常環境"


def main():
    us_out, us_raw = score_us(load_csv("us_daily.csv"))
    tw_out, tw_raw = score_tw(load_csv("tw_daily.csv"))
    us_out.to_csv(os.path.join(DATA, "scores_us.csv"), float_format="%.4g")
    tw_out.to_csv(os.path.join(DATA, "scores_tw.csv"), float_format="%.4g")

    # 台股日期對齊「當時已知」的美股分數（美股收盤早於台股隔日收盤）
    us_asof = us_out["score"].dropna()
    us_on_tw = pd.Series(us_asof.reindex(tw_out.index, method="ffill").values, index=tw_out.index)

    def rows(out, raw, extra=None):
        recs = []
        for d in out.index[out["score"].notna()]:
            r = {"date": d.strftime("%Y-%m-%d"), "score": round(float(out.at[d, "score"]), 1),
                 "zone": zone(out.at[d, "score"]), "退潮": bool(out.at[d, "退潮"]),
                 "recent": bool(out.at[d, "近期恐慌" if "近期恐慌" in out else "近期真恐慌"])}
            r["groups"] = {k[2:]: (None if pd.isna(v) else round(float(v), 1))
                           for k, v in out.loc[d].items() if k.startswith("組_")}
            r["indicators"] = {k[3:]: (None if pd.isna(v) else round(float(v), 1))
                               for k, v in out.loc[d].items() if k.startswith("指標_")}
            r["signals"] = {k[3:]: bool(v) for k, v in out.loc[d].items() if k.startswith("訊號_")}
            r["raw"] = {k: (None if pd.isna(v) else round(float(v), 4)) for k, v in raw.loc[d].items()}
            if extra is not None:
                r.update(extra(d))
            recs.append(r)
        return recs

    tw_rows = rows(tw_out, tw_raw, lambda d: {
        "us_score": None if pd.isna(us_on_tw[d]) else round(float(us_on_tw[d]), 1),
        "quadrant": quadrant(tw_out.at[d, "score"], us_on_tw[d])})
    us_rows = rows(us_out, us_raw)
    site = os.path.join(ROOT, "docs"); os.makedirs(site, exist_ok=True)
    data = {"updated": pd.Timestamp.now(tz="Asia/Taipei").strftime("%Y-%m-%d %H:%M"),
            "tw": tw_rows, "us": us_rows}
    with open(os.path.join(site, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    for name, out in [("美股", us_out), ("台股", tw_out)]:
        s = out["score"].dropna()
        print(f"{name}：{len(s)} 天有分數（{s.index.min().date() if len(s) else '-'} 起），"
              f"最新 {s.iloc[-1]:.0f}（{zone(s.iloc[-1])}）" if len(s) else f"{name}：尚無分數")


if __name__ == "__main__":
    main()
