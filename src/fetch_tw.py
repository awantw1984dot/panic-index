# -*- coding: utf-8 -*-
"""
台股資料（首次回補 3 年，之後每日增量）
- 證交所 FMTQIK：交易日清單與加權指數
- 證交所 MI_MARGN：融資餘額（張、金額）與個股融資 → 計算大盤融資維持率
- 證交所 MI_INDEX：個股收盤價（算維持率、跌破季線比例）、漲跌家數
- 期交所：外資台指期淨未平倉、臺指 VIX
- 冰水燈（課程 3-1）：MI_INDEX 的漲跌停家數、上漲類股數；FMTQIK 加權長歷史（5 年線）；OpenAPI 已發行股數（權值 100 大）
"""
import datetime as dt
import io
import os
import re
import time

import pandas as pd

from common import DATA, START, get, load_csv, num, roc_to_date, save_merge

MAX_MINUTES = float(os.environ.get("MAX_MINUTES", "300"))   # 預留時間把資料存回專案
T0 = time.time()
CLOSES = os.path.join(DATA, "tw_closes.csv.gz")
LONG_START = dt.date(2018, 1, 1)   # 加權指數長歷史：5 年線需要 2023 往前再 5 年
# 類股指數中屬於「合計」或槓桿反向的項目，不算進上漲類股數
SECTOR_SKIP = {"水泥窯製類指數", "塑膠化工類指數", "機電類指數", "化學生技醫療類指數", "電子工業類指數",
               "電子類兩倍槓桿指數", "電子類反向指數"}


def months(start, end):
    d = dt.date(start.year, start.month, 1)
    while d <= end:
        yield d
        d = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)


# ---------- 交易日與加權指數 ----------
def fetch_taiex(start, end):
    out = {}
    for m in months(start, end):
        j = get(f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={m:%Y%m%d}&response=json").json()
        for row in j.get("data") or []:
            out[pd.Timestamp(roc_to_date(row[0]))] = num(row[4])
    s = pd.Series(out, name="TAIEX").sort_index()
    return s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]


# ---------- 單日：融資與收盤價 ----------
def get_mi(ymd):
    ij = get(f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json").json()
    if ij.get("stat") != "OK":
        raise RuntimeError(f"{ymd} MI_INDEX 回應異常：{ij.get('stat')}")
    return ij


def parse_mi(ij):
    """收盤價、漲跌家數（含漲跌停）、類股漲跌（無上漲類股用）"""
    closes, rec = {}, {}
    up_sec = n_sec = 0
    for t in ij["tables"]:
        title = t.get("title") or ""
        if "每日收盤行情" in title:
            f = t["fields"]; ic, ip = f.index("證券代號"), f.index("收盤價")
            for row in t["data"]:
                p = num(row[ip])
                if p:
                    closes[row[ic].strip()] = p
        elif "漲跌證券數合計" in title:
            for row in t["data"]:   # row[2] 是「股票」欄，格式 '1,032(937)'：括號內為漲停／跌停
                m = re.match(r"([\d,]+)\(([\d,]+)\)", row[2].strip())
                total = num(re.sub(r"\(.*\)", "", row[2]))
                if row[0].startswith("上漲"):
                    rec["adv"], rec["limit_up"] = total, num(m.group(2)) if m else None
                if row[0].startswith("下跌"):
                    rec["dec"], rec["limit_down"] = total, num(m.group(2)) if m else None
        elif "價格指數(臺灣證券交易所)" in title:
            for row in t["data"]:
                name = row[0].strip()
                if name.endswith("類指數") and name not in SECTOR_SKIP:
                    pct = num(row[4])
                    if pct is not None:
                        n_sec += 1
                        up_sec += pct > 0
    if n_sec:
        rec["sector_up"], rec["sector_n"] = up_sec, n_sec
    return closes, rec


def fetch_day(d):
    ymd = d.strftime("%Y%m%d")
    mj = get(f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={ymd}&selectType=ALL&response=json").json()
    if mj.get("stat") != "OK":
        raise RuntimeError(f"{ymd} 融資回應異常：{mj.get('stat')}")
    closes, rec = parse_mi(get_mi(ymd))

    # 融資
    summ, detail = mj["tables"][0], mj["tables"][1]
    lots = amt = None
    for row in summ["data"]:
        if row[0].startswith("融資(交易單位)"): lots = num(row[5])
        if row[0].startswith("融資金額"): amt = num(row[5])
    mv = 0.0
    for row in detail["data"]:
        bal, p = num(row[6]), closes.get(row[0].strip())
        if bal and p:
            mv += bal * 1000 * p
    maint = mv / (amt * 1000) * 100 if amt else None

    rec.update({"margin_lots": lots, "margin_amt_k": amt, "margin_maint": maint})
    stock_closes = {k: v for k, v in closes.items() if re.fullmatch(r"\d{4}", k)}   # 普通股，算寬度用
    return rec, stock_closes


# ---------- 冰水燈用：回補、長歷史、股本 ----------
def backfill_mi(old, budget_min):
    """舊資料沒有漲跌停、類股欄位的日子，只重抓 MI_INDEX 補上（新到舊，時間到就停，下次接著補）"""
    if old.empty:
        return
    need = old.index[old["margin_maint"].notna() & (old["sector_up"].isna() if "sector_up" in old else True)]
    if not len(need):
        return
    print(f"冰水燈欄位回補：還有 {len(need)} 天")
    t1, recs = time.time(), {}
    for d in sorted(need, reverse=True):
        if (time.time() - t1) / 60 > budget_min or (time.time() - T0) / 60 > MAX_MINUTES:
            break
        try:
            _, rec = parse_mi(get_mi(d.strftime("%Y%m%d")))
            recs[d] = rec
        except Exception as e:
            print(f"  {d.date()} 回補失敗：{e}")
        if len(recs) >= 25:
            save_merge("tw_daily.csv", pd.DataFrame.from_dict(recs, orient="index")); recs.clear()
    if recs:
        save_merge("tw_daily.csv", pd.DataFrame.from_dict(recs, orient="index"))


def update_taiex_long():
    """data/taiex_long.csv：2018 起的加權指數（5 年線、10 月線用）；第一次回補，之後只補最近 2 個月"""
    old = load_csv("taiex_long.csv")
    today = dt.date.today()
    start = LONG_START if old.empty or old.index.min() > pd.Timestamp(LONG_START) + pd.Timedelta(days=10) \
        else (old.index.max() - pd.Timedelta(days=40)).date()
    try:
        s = fetch_taiex(start, today)
        save_merge("taiex_long.csv", s.to_frame())
        print(f"加權長歷史：{start} 起補 {len(s)} 天")
    except Exception as e:
        print(f"  加權長歷史失敗：{e}")


def update_shares():
    """data/tw_shares.csv：上市公司已發行普通股數（算市值排名，找權值 100 大）"""
    try:
        j = get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", wait=1).json()
        rows = {r["公司代號"].strip(): num(r.get("已發行普通股數或TDR原股發行股數")) for r in j}
        df = pd.Series({k: v for k, v in rows.items() if v}, name="shares").to_frame()
        df.index.name = "code"
        df.to_csv(os.path.join(DATA, "tw_shares.csv"))
        print(f"已發行股數：{len(df)} 家")
    except Exception as e:
        print(f"  已發行股數失敗：{e}（沿用舊檔）")


# ---------- 期交所 ----------
def fetch_futures(start, end):
    out = {}
    for m in months(start, end):
        last = min(dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1) - dt.timedelta(days=1), end)
        for back in range(6):
            e = last - dt.timedelta(days=back)
            if e < max(m, start):
                break
            r = get("https://www.taifex.com.tw/cht/3/futContractsDateDown", method="POST", wait=2,
                    data={"queryStartDate": f"{max(m, start):%Y/%m/%d}", "queryEndDate": f"{e:%Y/%m/%d}",
                          "commodityId": "TXF"})
            txt = r.content.decode("big5", errors="replace")
            if txt.startswith("日期"):
                break
        if not txt.startswith("日期"):
            print(f"  期貨 {m:%Y-%m} 無資料"); continue
        df = pd.read_csv(io.StringIO(txt))
        df = df[(df["商品名稱"].str.strip() == "臺股期貨") & (df["身份別"].str.strip() == "外資及陸資")]
        for _, row in df.iterrows():
            out[pd.Timestamp(row["日期"])] = float(row["多空未平倉口數淨額"])
    return pd.Series(out, name="fut_foreign_net_oi")


def fetch_tvix(start, end):
    out, missing = {}, []
    for m in months(start, end):
        r = get(f"https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/{m:%Y%m}new.txt", wait=1)
        txt = r.content.decode("big5", errors="replace")
        rows = re.findall(r"^(\d{8})\t\d+\t+([\d.]+)", txt, flags=re.M)   # 欄位間有多個 tab
        if not rows:
            missing.append(f"{m:%Y-%m}")
            print(f"  臺指VIX {m:%Y-%m} 原始內容：{txt[:400]!r}")
            continue
        for d, v in rows:
            out[pd.Timestamp(d.replace("/", ""))] = float(v)
    if missing:
        print(f"  臺指VIX 缺少月份：{missing}")
    return pd.Series(out, name="tvix")


# ---------- 市場寬度 ----------
def breadth(closes):
    ma = closes.rolling(60, min_periods=60).mean()
    valid = ma.notna() & closes.notna()
    below = (closes < ma) & valid
    pct = below.sum(axis=1) / valid.sum(axis=1).replace(0, float("nan")) * 100
    return pct.rename("below_ma60_pct")


def main():
    today = dt.date.today()
    old = load_csv("tw_daily.csv")
    closes = pd.read_csv(CLOSES, index_col=0, parse_dates=True) if os.path.exists(CLOSES) else pd.DataFrame()

    # 1. 交易日與指數：增量時只抓最近 2 個月
    t_start = START if old.empty else (old.index.max() - pd.Timedelta(days=40)).date()
    taiex = fetch_taiex(t_start, today)
    print(f"交易日：{len(taiex)} 天（{taiex.index.min().date()} ～ {taiex.index.max().date()}）")

    # 2. 逐日融資與收盤價（只抓還沒有的日子）
    done = set(old.index[old["margin_maint"].notna()]) if not old.empty else set()
    todo = [d for d in taiex.index if d not in done]
    print(f"需逐日抓取：{len(todo)} 天")
    recs, new_closes, n = {}, {}, 0

    def flush():
        nonlocal closes
        if recs:
            save_merge("tw_daily.csv", pd.DataFrame.from_dict(recs, orient="index"))
            recs.clear()
        if new_closes:
            closes = pd.DataFrame.from_dict(new_closes, orient="index").combine_first(closes).sort_index()
            closes.index.name = "date"
            closes.to_csv(CLOSES, float_format="%.6g", compression="gzip")
            new_closes.clear()

    for d in todo:
        if (time.time() - T0) / 60 > MAX_MINUTES:
            print("接近時間上限，先存檔，下次繼續"); break
        try:
            rec, cl = fetch_day(d.date())
            recs[d], new_closes[d] = rec, cl
            n += 1
        except Exception as e:
            print(f"  {d.date()} 失敗：{e}")
        if n and n % 25 == 0:
            flush(); print(f"  已完成 {n}/{len(todo)}（{(time.time()-T0)/60:.0f} 分鐘）")
    flush()

    # 3. 期交所（增量時抓最近 2 個月）
    f_start = START if old.empty or "tvix" not in old else (old["tvix"].dropna().index.max() - pd.Timedelta(days=40)).date()
    fut = fetch_futures(f_start, today)
    tvix = fetch_tvix(f_start, today)

    # 4. 合併、計算寬度
    df = pd.concat([taiex, fut, tvix], axis=1)
    df = df[df.index.isin(taiex.index) | df.index.isin(load_csv("tw_daily.csv").index)]
    df = save_merge("tw_daily.csv", df)
    if not closes.empty:
        df["below_ma60_pct"] = breadth(closes)
        df = save_merge("tw_daily.csv", df)

    # 5. 冰水燈用資料
    update_taiex_long()
    update_shares()
    backfill_mi(load_csv("tw_daily.csv"), float(os.environ.get("BACKFILL_MINUTES", "60")))
    df = load_csv("tw_daily.csv")

    print(f"\n台股資料：{len(df)} 列，{df.index.min().date()} ～ {df.index.max().date()}")
    print("缺值數：", df.isna().sum().to_dict())
    print("最近 3 天：")
    print(df.tail(3).round(2).to_string())


if __name__ == "__main__":
    main()
