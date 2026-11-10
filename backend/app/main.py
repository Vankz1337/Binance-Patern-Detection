from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
import asyncio
import time
from fastapi.middleware.cors import CORSMiddleware
import httpx

from .analysis import analyze_ohlcv
from .finder import scan_pattern

app = FastAPI(title="Invictus Web 2.0 API", version="2.0.0-alpha.20")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

BINANCE_ENDPOINTS = (
    # Public market-data endpoint documented by Binance. Using it first
    # avoids the certificate/hostname problem seen with api.binance.com on
    # the local Windows environment while keeping official API fallbacks.
    "https://data-api.binance.vision",
    "https://api-gcp.binance.com",
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
)

@app.get("/api/health")
async def health():
    return {"ok": True, "service": "invictus-backend", "version": app.version}

@app.get("/api/market/klines")
async def klines(symbol: str = Query(..., min_length=5), interval: str = Query(...), limit: int = Query(300, ge=50, le=1000)):
    last_error: Exception | None = None
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    for base in BINANCE_ENDPOINTS:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(8.0, connect=5.0),
                headers={"User-Agent": "Invictus-Web-2.0"},
                trust_env=False,
                follow_redirects=True,
            ) as client:
                response = await client.get(f"{base}/api/v3/klines", params=params)
                response.raise_for_status()
                rows = response.json()
            if not isinstance(rows, list) or not rows:
                raise ValueError("Binance returned no candles")
            cleaned = []
            for r in rows:
                cleaned.append({"time": int(r[0]) // 1000, "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])})
            cleaned.sort(key=lambda x: x["time"])
            unique = []
            for item in cleaned:
                if unique and item["time"] == unique[-1]["time"]:
                    unique[-1] = item
                else:
                    unique.append(item)
            return unique
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
    raise HTTPException(status_code=502, detail=f"Binance market data error after failover: {last_error}")


RADAR_COINS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
RADAR_TFS = ("1m", "5m", "15m", "1h", "4h", "1d")

async def _scan_one(symbol: str, interval: str) -> dict:
    try:
        candles = await klines(symbol, interval, 180)
        result = analyze_ohlcv(candles)
        pat = result.get("pattern")
        rank = {"CONFIRMED": 3, "POTENTIAL": 2, "FORMING": 1}.get((pat or {}).get("status"), 0)
        return {
            "symbol": symbol,
            "interval": interval,
            "structure": result.get("structure", "AMBIGUOUS"),
            "pattern": pat,
            "priority": rank,
        }
    except Exception as exc:
        return {"symbol": symbol, "interval": interval, "structure": "UNKNOWN", "pattern": None, "priority": 0, "error": str(exc)}

@app.get("/api/radar")
async def radar():
    # Bounded concurrency keeps a full 36-cell scan responsive and avoids
    # hammering a single public exchange endpoint during a refresh.
    sem = asyncio.Semaphore(6)
    async def limited(symbol: str, interval: str):
        async with sem:
            return await _scan_one(symbol, interval)
    results = await asyncio.gather(*(limited(s, tf) for s in RADAR_COINS for tf in RADAR_TFS))
    results = sorted(results, key=lambda x: (x.get("priority", 0), (x.get("pattern") or {}).get("quality", 0)), reverse=True)
    return {"items": results, "updatedAt": time.time_ns() // 1_000_000}

@app.get("/api/analysis")
async def analysis(symbol: str = Query(...), interval: str = Query(...), limit: int = Query(300, ge=80, le=1000)):
    candles = await klines(symbol, interval, limit)
    return analyze_ohlcv(candles)


@app.get("/api/pattern-finder")
async def pattern_finder(
    pattern: str = Query(..., min_length=3),
    interval: str = Query("1d"),
    sensitivity: str = Query("balanced"),
    universe: int = Query(250, ge=50, le=500),
):
    allowed = {"broad", "balanced", "strict"}
    if sensitivity not in allowed:
        raise HTTPException(status_code=400, detail="sensitivity must be broad, balanced, or strict")
    return await scan_pattern(pattern.upper(), interval, sensitivity, universe)

