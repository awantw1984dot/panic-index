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


# 絕對水位：依各指標長期歷史常態設定的參考點（數值 → 0~100 分）
# 只看近 2 年百分位，平靜期稍有波動就會被誇大，所以與絕對水位各占一半
ANCHORS = {
    "VIX": [(12, 0), (16, 30), (20, 55), (25, 75), (30, 85), (40, 95), (50, 100)],
    "VIX期限結構": [(0.80, 0), (0.88, 40), (0.95, 65), (1.00, 80), (1.10, 95), (1.20, 100)],
    "MOVE": [(60, 0), (80, 25), (100, 50), (120, 75), (150, 92), (180, 100)],
    "HY利差": [(2.5, 0), (3.5, 20), (4.5, 50), (5.5, 70), (7, 85), (9, 95), (12, 100)],
    "IG利差": [(0.7, 0), (1.0, 20), (1.3, 50), (1.6, 70), (2.0, 85), (3.0, 97), (4.0, 100)],
    "JNK/IEF回撤": [(0, 0), (0.02, 30), (0.05, 60), (0.08, 80), (0.12, 95), (0.20, 100)],
    "臺指VIX": [(12, 0), (16, 25), (20, 50), (25, 70), (30, 82), (40, 95), (50, 100)],
    "融資維持率": [(130, 100), (135, 97), (145, 85), (155, 70), (165, 50), (175, 30), (190, 0)],
    "融資10日變化": [(-12, 100), (-8, 90), (-5, 75), (-2, 55), (0, 40), (3, 20), (6, 0)],
    "外資期貨10日變化": [(-30000, 100), (-15000, 80), (-5000, 60), (0, 45), (10000, 20), (25000, 0)],
    "跌破季線比例": [(20, 0), (40, 30), (55, 55), (70, 80), (85, 95), (95, 100)],
}


def anchor(s, name):
    xs, ys = zip(*ANCHORS[name])
    return pd.Series(np.interp(s, xs, ys), index=s.index).where(s.notna())


def blend(s, name, invert=False, anchor_only_ok=False):
    """相對水位（近 2 年百分位）與絕對水位各半；百分位尚未暖機前不給分
    anchor_only_ok：歷史資料不足時（臺指VIX 期交所只提供近 4 個月），先只用絕對水位"""
    p = pct_rank(s)
    if invert:
        p = 100 - p
    a = anchor(s, name)
    out = (p + a.reindex(p.index)) / 2
    if anchor_only_ok:
        out = out.reindex(a.index).fillna(a)
    return out


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
    c["HY利差"] = blend(us["HY_OAS"], "HY利差")
    c["IG利差"] = blend(us["IG_OAS"], "IG利差")
    c["JNK/IEF回撤"] = blend(1 - ratio / ratio.rolling(252, min_periods=60).max(), "JNK/IEF回撤")
    c["VIX"] = blend(us["VIX"], "VIX")
    c["VIX期限結構"] = blend(term, "VIX期限結構")
    c["MOVE"] = blend(us["MOVE"], "MOVE")
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
    c["融資維持率(反向)"] = blend(tw["margin_maint"], "融資維持率", invert=True)
    c["融資10日變化(反向)"] = blend(tw["margin_amt_k"].pct_change(10) * 100, "融資10日變化", invert=True)
    c["臺指VIX"] = blend(tw["tvix"], "臺指VIX", anchor_only_ok=True)
    c["外資期貨淨空單10日變化"] = blend(tw["fut_foreign_net_oi"].diff(10), "外資期貨10日變化", invert=True)
    c["跌破季線比例"] = blend(tw["below_ma60_pct"], "跌破季線比例")
    score, g = weighted(c, TW_GROUPS)

    # 退潮訊號：近 20 天分數曾 ≥ 75（真正的特賣會）才檢查，避免小波動也觸發
    recent = (score >= 75).astype(float).rolling(20, min_periods=1).max() == 1
    m, b, v = tw["margin_maint"], tw["below_ma60_pct"], tw["tvix"]
    checks = pd.DataFrame({
        "融資維持率止跌回升": (m.diff(3) > 0) & (m > m.rolling(10).min() * 1.01),
        "市場寬度改善": b.diff(5) < 0,
        "臺指VIX回落": (v.diff(5) < 0) & (v < v.rolling(10).max() * 0.9),
    })
    out = pd.concat([score.rename("score"), g.add_prefix("組_"), c.add_prefix("指標_"), checks.add_prefix("訊號_")], axis=1)
    checks = checks.astype("float")
    checks.loc[v.isna(), "臺指VIX回落"] = np.nan          # 沒有臺指VIX資料的日子不列入
    passed = checks.fillna(1).astype(bool).all(axis=1) & (checks.notna().sum(axis=1) >= 2)
    out["近期恐慌"] = recent
    out["退潮"] = recent & passed
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
            r["signals"] = {k[3:]: (None if pd.isna(v) else bool(v)) for k, v in out.loc[d].items() if k.startswith("訊號_")}
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

    # 給 iPhone 捷徑讀取的精簡狀態：只在狀態改變時才有 events
    t, p = tw_rows[-1], (tw_rows[-2] if len(tw_rows) > 1 else None)
    u, up = us_rows[-1], (us_rows[-2] if len(us_rows) > 1 else None)
    events = []
    if p and t["zone"] != p["zone"]:
        events.append(f"台股{t['zone']} {t['score']:.0f}（原本{p['zone']}）")
    if up and u["zone"] != up["zone"]:
        events.append(f"美股{u['zone']} {u['score']:.0f}（原本{up['zone']}）")
    if p and t["quadrant"] != p["quadrant"]:
        events.append(f"狀態改為{t['quadrant']}")
    if t["退潮"] and not (p and p["退潮"]):
        events.append("台股可以進場搶購：退潮訊號觸發")
    if u["退潮"] and not (up and up["退潮"]):
        events.append("美股退潮訊號觸發")
    status = {"updated": data["updated"], "tw_date": t["date"], "us_date": u["date"],
              "tw_score": round(t["score"]), "tw_zone": t["zone"], "us_score": round(u["score"]), "us_zone": u["zone"],
              "quadrant": t["quadrant"], "events": events,
              "summary": f"台股 {t['score']:.0f} {t['zone']}｜美股 {u['score']:.0f} {u['zone']}｜{t['quadrant']}"}
    with open(os.path.join(site, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)
    print("通知事件：", events or "無")

    for name, out in [("美股", us_out), ("台股", tw_out)]:
        s = out["score"].dropna()
        print(f"{name}：{len(s)} 天有分數（{s.index.min().date() if len(s) else '-'} 起），"
              f"最新 {s.iloc[-1]:.0f}（{zone(s.iloc[-1])}）" if len(s) else f"{name}：尚無分數")


if __name__ == "__main__":
    main()
