from __future__ import annotations

from statistics import mean
from typing import Any

from .patterns.engine import detect_pattern, build_context


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    value = values[0]
    for x in values[1:]:
        value = x * k + value * (1 - k)
    return value


def atr(candles: list[dict[str, Any]], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs: list[float] = []
    for prev, cur in zip(candles, candles[1:]):
        trs.append(max(cur["high"] - cur["low"], abs(cur["high"] - prev["close"]), abs(cur["low"] - prev["close"])))
    sample = trs[-period:]
    return mean(sample) if sample else 0.0


def structure(candles: list[dict[str, Any]]) -> str:
    closes = [c["close"] for c in candles]
    if len(closes) < 40:
        return "AMBIGUOUS"
    fast = mean(closes[-10:])
    slow = mean(closes[-30:])
    drift = closes[-1] / max(closes[-31], 1) - 1
    if fast > slow * 1.002 and drift > 0.004:
        return "UPTREND"
    if fast < slow * 0.998 and drift < -0.004:
        return "DOWNTREND"
    return "SIDEWAYS"


def analyze_ohlcv(candles: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [c["close"] for c in candles]
    a = atr(candles)
    pattern = detect_pattern(candles, a)
    return {
        "pattern": pattern,
        "structure": structure(candles),
        "atr": a,
        "ema20": ema(closes, 20),
        "ema50": ema(closes, 50),
        "trendLines": build_context(candles, a),
    }

