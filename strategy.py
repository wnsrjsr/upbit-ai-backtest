import pandas as pd


def _rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-12)
    return 100 - (100 / (1 + rs))


def analyze(df):
    """
    규칙 기반 점수화 전략(학습형 머신러닝 모델은 아님).
    점수 범위는 대략 -4~+4이며, 지표 조합으로 진입/청산 신호를 만든다.
    """
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    rsi = _rsi(close)

    vol_avg = volume.rolling(20).mean()
    latest = len(df) - 1
    score = 0
    reasons = []

    if ema9.iloc[latest] > ema21.iloc[latest]:
        score += 1
        reasons.append("EMA9>EMA21")
    else:
        score -= 1
        reasons.append("EMA9<EMA21")

    if close.iloc[latest] > ema50.iloc[latest]:
        score += 1
        reasons.append("종가>EMA50")
    else:
        score -= 1
        reasons.append("종가<EMA50")

    if hist.iloc[latest] > 0 and hist.iloc[latest] >= hist.iloc[latest-1]:
        score += 1
        reasons.append("MACD 모멘텀 상승")
    elif hist.iloc[latest] < 0:
        score -= 1
        reasons.append("MACD 모멘텀 약세")

    r = float(rsi.iloc[latest])
    if 45 <= r <= 68:
        score += 1
        reasons.append(f"RSI 양호({r:.1f})")
    elif r > 75:
        score -= 1
        reasons.append(f"RSI 과열({r:.1f})")
    elif r < 30:
        reasons.append(f"RSI 과매도({r:.1f})")

    if vol_avg.iloc[latest] and volume.iloc[latest] > vol_avg.iloc[latest] * 1.2:
        if close.iloc[latest] >= close.iloc[latest-1]:
            score += 1
            reasons.append("거래량 동반 상승")

    return score, ", ".join(reasons)
