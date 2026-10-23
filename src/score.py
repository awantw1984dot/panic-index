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

TW_READY = (21, 0)    # 台股融資資料約台北 21:00 公布
US_READY_MIN = 30     # 美股收盤後 30 分鐘才視為已有收盤資料


def expected_dates(now=None):
    """依交易所行事曆推算「此刻應該已經有」的最新交易日（台股、美股）；行事曆套件不可用時回傳 (None, None)"""
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    try:
        import exchange_calendars as xc
    except Exception:
        return None, None
    tpe = now.tz_convert("Asia/Taipei")
    d = pd.Timestamp(tpe.date())
    xtai = xc.get_calendar("XTAI")
    sess = xtai.sessions_in_range(d - pd.Timedelta(days=20), d)
    if len(sess) and sess[-1] == d and (tpe.hour, tpe.minute) < TW_READY:
        sess = sess[:-1]
    tw_exp = sess[-1] if len(sess) else None
    xnys = xc.get_calendar("XNYS")
    et_d = pd.Timestamp(now.tz_convert("America/New_York").date())
    us_exp = None
    for s in reversed(xnys.sessions_in_range(et_d - pd.Timedelta(days=20), et_d)):
        if xnys.session_close(s) + pd.Timedelta(minutes=US_READY_MIN) <= now:
            us_exp = s
            break
    return tw_exp, us_exp


def freshness(tw_date, us_date, now=None):
    """最新資料日期是否落後於「應有」的交易日；回傳提醒文字清單（空清單 = 資料都是最新）"""
    tw_exp, us_exp = expected_dates(now)
    md = lambda s: str(s)[5:10].replace("-", "/")
    msgs = []
    if tw_exp is None and us_exp is None:   # 沒有行事曆時退回舊規則：超過 2／3 個營業日
        today = (now if now is not None else pd.Timestamp.now(tz="UTC")).tz_convert("Asia/Taipei").tz_localize(None).normalize()
        lag = lambda x: len(pd.bdate_range(pd.Timestamp(x) + pd.Timedelta(days=1), today)) - 1
        if lag(tw_date) > 2:
            msgs.append(f"台股停在 {md(tw_date)}")
        if lag(us_date) > 3:
            msgs.append(f"美股停在 {md(us_date)}")
        return msgs
    if tw_exp is not None and pd.Timestamp(tw_date) < tw_exp:
        msgs.append(f"台股缺 {md(tw_exp.date())} 資料（停在 {md(tw_date)}）")
    if us_exp is not None and pd.Timestamp(us_date) < us_exp:
        msgs.append(f"美股缺 {md(us_exp.date())} 收盤資料（停在 {md(us_date)}）")
    return msgs

WIN, MINP = 504, 252          # 百分位視窗約 2 年，至少 1 年資料才給分
PANIC = 60                    # 四格判斷：≥60 視為恐慌側
HEAT = 15                     # 升溫警示：5 個交易日上升 ≥15 分，且分數在 40～80 之間
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


# 合理範圍：超出視為來源異常（格式改版、抓錯欄位），當作缺值並記錄
VALID = {
    "VIX": (5, 150), "VIX3M": (5, 150), "MOVE": (20, 400), "HY_OAS": (0.5, 25), "IG_OAS": (0.2, 8),
    "JNK": (20, 300), "IEF": (20, 300), "STLFSI": (-5, 15), "SPX": (500, 50000),
    "TAIEX": (5000, 200000), "margin_maint": (100, 400), "margin_amt_k": (1e7, 5e9),
    "tvix": (5, 150), "below_ma60_pct": (0, 100), "fut_foreign_net_oi": (-500000, 500000),
}
ANOMALIES = []


def sanitize(df, label):
    df = df.copy()
    for c, (lo, hi) in VALID.items():
        if c in df:
            bad = df[c].notna() & ~df[c].between(lo, hi)
            if bad.any():
                ANOMALIES.append(f"{label} {c}：{int(bad.sum())} 筆超出 {lo}～{hi}（最近 {df.index[bad].max().date()}）")
                df.loc[bad, c] = np.nan
    return df


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


def heat_of(sc, i):
    """升溫：5 個交易日上升 ≥ HEAT 分，且分數在 40～80 之間"""
    if i < 5 or pd.isna(sc.iloc[i]) or pd.isna(sc.iloc[i - 5]):
        return False
    return bool(sc.iloc[i] - sc.iloc[i - 5] >= HEAT and 40 <= sc.iloc[i] < 80)


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
    us = sanitize(us, "美股")
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
    raw = us[["VIX", "VIX3M", "MOVE", "STLFSI", "SPX", "SOX"]].copy()   # 不含 ICE 利差原始值（授權限制）
    raw["VIX期限結構"] = term
    raw["JNK/IEF"] = ratio
    return out, raw


# ---------------- 台股 ----------------
def score_tw(tw):
    tw = sanitize(tw, "台股")
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
    us_in = load_csv("us_daily.csv").drop(columns=["HY_OAS", "IG_OAS"], errors="ignore")
    ice = load_csv("fred_ice.csv")   # ICE 利差只存在執行環境中，不公開
    us_in = us_in.join(ice, how="outer") if not ice.empty else us_in.reindex(columns=[*us_in.columns, "HY_OAS", "IG_OAS"])
    us_out, us_raw = score_us(us_in)
    tw_out, tw_raw = score_tw(load_csv("tw_daily.csv"))
    us_out.to_csv(os.path.join(DATA, "scores_us.csv"), float_format="%.4g")
    tw_out.to_csv(os.path.join(DATA, "scores_tw.csv"), float_format="%.4g")

    # 台股日期對齊「當時已知」的美股分數（美股收盤早於台股隔日收盤）
    us_asof = us_out["score"].dropna()
    us_on_tw = pd.Series(us_asof.reindex(tw_out.index, method="ffill").values, index=tw_out.index)

    def rows(out, raw, extra=None):
        recs = []
        for d in out.index[out["score"].notna()]:
            i = out.index.get_loc(d)
            sc = out["score"]
            prev5 = sc.iloc[i - 5] if i >= 5 else np.nan
            chg5 = None if pd.isna(prev5) else round(float(sc.iloc[i] - prev5), 1)
            r = {"date": d.strftime("%Y-%m-%d"), "score": round(float(out.at[d, "score"]), 1),
                 "chg5": chg5, "heat": heat_of(sc, i), "heat_start": heat_of(sc, i) and not any(heat_of(sc, k) for k in range(max(0, i - 10), i)),
                 "zone": zone(out.at[d, "score"]), "退潮": bool(out.at[d, "退潮"]),
                 "recent": bool(out.at[d, "近期恐慌" if "近期恐慌" in out else "近期真恐慌"])}
            r["groups"] = {k[2:]: (None if pd.isna(v) else round(float(v), 1))
                           for k, v in out.loc[d].items() if k.startswith("組_")}
            r["indicators"] = {k[3:]: (None if pd.isna(v) else round(float(v), 1))
                               for k, v in out.loc[d].items() if k.startswith("指標_")}
            r["missing"] = [k for k, v in r["indicators"].items() if v is None]
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
    cal = []   # 經濟數據公布日（fetch_us.py 產生）＋手動維護的事件（台積電法說會等）
    for fn in ["events.json", "manual_events.json"]:
        ep = os.path.join(DATA, fn)
        if os.path.exists(ep):
            with open(ep, encoding="utf-8") as f:
                cal += json.load(f)
    cal = sorted(cal, key=lambda e: e["date"])
    stale = freshness(tw_rows[-1]["date"], us_rows[-1]["date"])   # 依交易所行事曆檢查資料是否缺日
    data = {"updated": pd.Timestamp.now(tz="Asia/Taipei").strftime("%Y-%m-%d %H:%M"),
            "tw": tw_rows, "us": us_rows, "events": cal, "stale": stale}
    with open(os.path.join(site, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    # 給 iPhone 捷徑讀取的精簡狀態：與「上一次產生的 status.json」比較，只在狀態改變時才有 events
    # （不比較最近兩個交易日，否則早上只更新美股時，會把前一晚已通知的台股變化再通知一次）
    t, u = tw_rows[-1], us_rows[-1]
    sp = os.path.join(site, "status.json")
    prev = {}
    if os.path.exists(sp):
        try:
            with open(sp, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}
    if not prev.get("tw_zone"):   # 第一次產生：改和前一個交易日比較
        p, up = (tw_rows[-2] if len(tw_rows) > 1 else t), (us_rows[-2] if len(us_rows) > 1 else u)
        prev = {"tw_zone": p["zone"], "us_zone": up["zone"], "quadrant": p["quadrant"],
                "tw_exit": p["退潮"], "us_exit": up["退潮"]}
    events = []
    if stale and stale != prev.get("stale"):   # stale 已在上方依交易所行事曆算出
        events.append("資料未更新：" + "、".join(stale))
    if t["退潮"] and not prev.get("tw_exit"):
        events.append("台股可以進場搶購")
    if t["zone"] != prev.get("tw_zone"):
        events.append(f"台股{prev.get('tw_zone')}→{t['zone']}")
    if u["zone"] != prev.get("us_zone"):
        events.append(f"美股{prev.get('us_zone')}→{u['zone']}")
    if t["quadrant"] != prev.get("quadrant"):
        events.append(f"狀態→{t['quadrant']}")
    if u["退潮"] and not prev.get("us_exit"):
        events.append("美股退潮訊號觸發")
    # 升溫：10 個交易日內只提醒一次；用日期判斷，避免早晚兩次更新重複通知
    if t["heat_start"] and prev.get("tw_heat_date") != t["date"]:
        events.append(f"台股升溫：5日+{t['chg5']:.0f}")
    if u["heat_start"] and prev.get("us_heat_date") != u["date"]:
        events.append(f"美股升溫：5日+{u['chg5']:.0f}")
    status = {"updated": data["updated"], "tw_date": t["date"], "us_date": u["date"],
              "tw_score": round(t["score"]), "tw_zone": t["zone"], "us_score": round(u["score"]), "us_zone": u["zone"],
              "quadrant": t["quadrant"], "tw_exit": t["退潮"], "us_exit": u["退潮"], "stale": stale, "anomalies": ANOMALIES[-5:], "tw_heat": t["heat"], "us_heat": u["heat"],
              "tw_heat_date": t["date"] if t["heat_start"] else prev.get("tw_heat_date"),
              "us_heat_date": u["date"] if u["heat_start"] else prev.get("us_heat_date"), "events": events,
              "summary": f"台股 {t['score']:.0f} {t['zone']}｜美股 {u['score']:.0f} {u['zone']}｜{t['quadrant']}",
              # 給捷徑通知用：標題放重點，內容一行；沒有事件時 body 為空字串
              "title": f"{t['quadrant']}｜台股 {t['score']:.0f}・美股 {u['score']:.0f}",
              "body": "，".join(events)}
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)
    print("通知事件：", events or "無")
    print("資料異常：", ANOMALIES or "無")

    for name, out in [("美股", us_out), ("台股", tw_out)]:
        s = out["score"].dropna()
        print(f"{name}：{len(s)} 天有分數（{s.index.min().date() if len(s) else '-'} 起），"
              f"最新 {s.iloc[-1]:.0f}（{zone(s.iloc[-1])}）" if len(s) else f"{name}：尚無分數")


if __name__ == "__main__":
    main()
