# indicators.py — 纯 pandas 技术指标 + 取数(透明、不依赖 pandas-ta)
# 所有脚本共用。指标都是几行能看懂的实现，方便你自己核对/修改。
import pandas as pd
import yfinance as yf


def load(ticker, period="2y", interval="1d", start=None, end=None, retries=3):
    """下载日线并清洗成单层列；带重试(Yahoo 偶尔 429)。"""
    import time
    for i in range(retries):
        if start or end:
            df = yf.download(ticker, start=start, end=end, interval=interval,
                             auto_adjust=True, progress=False)
        else:
            df = yf.download(ticker, period=period, interval=interval,
                             auto_adjust=True, progress=False)
        if df is not None and len(df) > 0:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        time.sleep(2 * (i + 1))
    return None


def sma(s, n):
    return s.rolling(n).mean()


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0)
    dn = -d.clip(upper=0)
    rs = up.ewm(alpha=1/n, adjust=False).mean() / dn.ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + rs)


def macd(close, fast=12, slow=26, sig=9):
    m = ema(close, fast) - ema(close, slow)
    s = ema(m, sig)
    return m, s, m - s   # macd 线, 信号线, 柱(hist)


def atr(df, n=14):
    """平均真实波幅 —— 用来量化'波动有多大'，是定止损/仓位的关键。"""
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()


def adx(df, n=14):
    """ADX/+DI/-DI —— ADX 高=有趋势，低(<20~25)=震荡(KhanSaab 纪律里不进场)。"""
    h, l, c = df["High"], df["Low"], df["Close"]
    up = h.diff()
    dn = -l.diff()
    plus_dm = ((up > dn) & (up > 0)) * up
    minus_dm = ((dn > up) & (dn > 0)) * dn
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1/n, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/n, adjust=False).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=1/n, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
    adx_ = dx.ewm(alpha=1/n, adjust=False).mean()
    return adx_, plus_di, minus_di
