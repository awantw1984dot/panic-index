# 測試 CBOE 備援：故意把 yfinance 的 VIX 清掉，看能否補回
import sys; sys.path.insert(0, "src")
import pandas as pd
import fetch_us as F
df = F.fetch_yf()
orig = df["VIX"].copy()
df.loc[df.index[-30:], "VIX"] = float("nan")
df = F.fill_from_cboe(df)
diff = (df["VIX"] - orig).abs().loc[orig.index[-30:]]
print("補回筆數", df["VIX"].loc[orig.index[-30:]].notna().sum(), "/ 30，最大差異", round(diff.max(), 4))
print(df[["VIX", "VIX3M"]].tail(3))
