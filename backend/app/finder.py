from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .analysis import atr
from .patterns.engine import detect_patterns

BINANCE_ENDPOINTS = (
    "https://data-api.binance.vision",
    "https://api-gcp.binance.com",
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
)

PATTERN_ALIASES = {
    "BULLISH_FLAG": "BULLISH FLAG",
    "BEARISH_FLAG": "BEARISH FLAG",
    "DOUBLE_BOTTOM": "DOUBLE BOTTOM",
    "DOUBLE_TOP": "DOUBLE TOP",
    "HEAD_AND_SHOULDERS": "HEAD & SHOULDERS",
    "INVERSE_HEAD_AND_SHOULDERS": "INVERSE H&S",
    "ASCENDING_TRIANGLE": "ASCENDING TRIANGLE",
    "DESCENDING_TRIANGLE": "DESCENDING TRIANGLE",
    "SYMMETRICAL_TRIANGLE": "SYMMETRICAL TRIANGLE",
    "RISING_WEDGE": "RISING WEDGE",
    "FALLING_WEDGE": "FALLING WEDGE",
    "BULLISH_PENNANT": "BULLISH PENNANT",
    "BEARISH_PENNANT": "BEARISH PENNANT",
    "RECTANGLE": "RECTANGLE",
}

_symbol_cache: tuple[float, list[str]] | None = None
_symbol_lock = asyncio.Lock()

async def _get_json(client: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None):
    last: Exception | None = None
    for base in BINANCE_ENDPOINTS:
        try:
            r = await client.get(f"{base}{path}", params=params)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
    raise RuntimeError(f"Binance request failed: {last}")

async def discover_usdt_symbols(limit: int) -> list[str]:
    global _symbol_cache
    now = time.monotonic()
    if _symbol_cache and now - _symbol_cache[0] < 300:
        return _symbol_cache[1][:limit]
    async with _symbol_lock:
        now = time.monotonic()
        if _symbol_cache and now - _symbol_cache[0] < 300:
            return _symbol_cache[1][:limit]
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=5.0), trust_env=False, headers={"User-Agent": "Invictus-Web-2.0"}) as client:
            info = await _get_json(client, "/api/v3/exchangeInfo")
            tickers = await _get_json(client, "/api/v3/ticker/24hr")
        allowed = set()
        for s in info.get("symbols", []):
            if s.get("status") != "TRADING":
                continue
            if s.get("quoteAsset") != "USDT":
                continue
            if not s.get("isSpotTradingAllowed", True):
                continue
            sym = s.get("symbol", "")
            if not sym or any(sym.endswith(x) for x in ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")):
                continue
            allowed.add(sym)
        ranked: list[tuple[float, str]] = []
        for t in tickers if isinstance(tickers, list) else []:
            sym = t.get("symbol")
            if sym not in allowed:
                continue
            try:
                volume = float(t.get("quoteVolume", 0.0))
            except (TypeError, ValueError):
                volume = 0.0
            ranked.append((volume, sym))
        ranked.sort(reverse=True)
        symbols = [sym for _, sym in ranked]
        _symbol_cache = (time.monotonic(), symbols)
        return symbols[:limit]

async def fetch_klines(client: httpx.AsyncClient, symbol: str, interval: str, limit: int = 180) -> list[dict[str, float | int]]:
    rows = await _get_json(client, "/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not isinstance(rows, list) or not rows:
        raise ValueError("no candles")
    out = []
    for r in rows:
        out.append({"time": int(r[0]) // 1000, "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])})
    return out

async def scan_pattern(pattern: str, interval: str, sensitivity: str = "balanced", universe: int = 250) -> dict[str, Any]:
    symbols = await discover_usdt_symbols(universe)
    threshold = {"broad": 58, "balanced": 70, "strict": 80}.get(sensitivity, 70)
    timeout = httpx.Timeout(10.0, connect=6.0)
    sem = asyncio.Semaphore(10)
    matches: list[dict[str, Any]] = []
    scanned = 0

    async with httpx.AsyncClient(timeout=timeout, trust_env=False, headers={"User-Agent": "Invictus-Pattern-Finder"}) as client:
        async def one(symbol: str):
            async with sem:
                try:
                    candles = await fetch_klines(client, symbol, interval, 180)
                    a = atr(candles)
                    candidates = detect_patterns(candles, a, include_forming=True)
                    wanted = [p for p in candidates if p.get("name") == pattern and int(p.get("quality", 0)) >= threshold]
                    if not wanted:
                        return None
                    p = wanted[0]
                    return {
                        "symbol": symbol,
                        "interval": interval,
                        "pattern": p,
                        "match": int(p.get("quality", 0)),
                        "price": candles[-1]["close"],
                        "status": p.get("lifecycle") or p.get("status"),
                        "signals": sum(1 for c in p.get("checks", []) if c.get("ok")),
                    }
                except Exception:
                    return None
        results = await asyncio.gather(*(one(sym) for sym in symbols))
        scanned = len(symbols)
    for item in results:
        if item:
            matches.append(item)
    matches.sort(key=lambda x: (x["match"], x["signals"]), reverse=True)
    return {
        "pattern": pattern,
        "patternLabel": PATTERN_ALIASES.get(pattern, pattern.replace("_", " ")),
        "interval": interval,
        "sensitivity": sensitivity,
        "scanned": scanned,
        "matches": matches,
        "updatedAt": int(time.time() * 1000),
    }

