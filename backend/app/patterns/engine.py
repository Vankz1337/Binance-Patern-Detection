from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable


@dataclass(frozen=True)
class Pivot:
    index: int
    time: int
    price: float
    kind: str


def _pivot_dict(p: Pivot, role: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {
        "index": int(p.index),
        "time": int(p.time),
        "price": float(p.price),
        "kind": str(p.kind),
    }
    if role:
        d["role"] = role
    return d


def _finite_candles(candles: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for c in candles:
        try:
            t = int(c["time"])
            o, h, l, cl, v = (float(c[k]) for k in ("open", "high", "low", "close", "volume"))
        except (KeyError, TypeError, ValueError):
            continue
        if t <= 0 or not all(x == x for x in (o, h, l, cl, v)):
            continue
        if h < max(o, cl) or l > min(o, cl) or h < l:
            continue
        cleaned.append({"time": t, "open": o, "high": h, "low": l, "close": cl, "volume": v})
    cleaned.sort(key=lambda c: int(c["time"]))
    unique: list[dict[str, Any]] = []
    for c in cleaned:
        if unique and int(c["time"]) == int(unique[-1]["time"]):
            unique[-1] = c
        else:
            unique.append(c)
    for i, c in enumerate(unique):
        c["index"] = i
    return unique


def pivots(candles: list[dict[str, Any]], left: int = 3, right: int = 3, min_separation: int = 3) -> list[Pivot]:
    c = _finite_candles(candles)
    out: list[Pivot] = []
    for i in range(left, len(c) - right):
        hi = float(c[i]["high"])
        lo = float(c[i]["low"])
        left_h = max(float(x["high"]) for x in c[i-left:i])
        right_h = max(float(x["high"]) for x in c[i+1:i+1+right])
        left_l = min(float(x["low"]) for x in c[i-left:i])
        right_l = min(float(x["low"]) for x in c[i+1:i+1+right])
        is_high = hi >= left_h and hi >= right_h and (hi > left_h or hi > right_h)
        is_low = lo <= left_l and lo <= right_l and (lo < left_l or lo < right_l)
        if is_high:
            out.append(Pivot(i, int(c[i]["time"]), hi, "HIGH"))
        if is_low:
            out.append(Pivot(i, int(c[i]["time"]), lo, "LOW"))
    out.sort(key=lambda p: (p.index, p.kind))
    filtered: list[Pivot] = []
    for p in out:
        if not filtered:
            filtered.append(p)
            continue
        prev = filtered[-1]
        if p.kind == prev.kind and p.index - prev.index <= min_separation:
            stronger = p if ((p.kind == "HIGH" and p.price >= prev.price) or (p.kind == "LOW" and p.price <= prev.price)) else prev
            filtered[-1] = stronger
        else:
            filtered.append(p)
    return filtered


def quality(parts: list[float]) -> int:
    if not parts:
        return 0
    return max(0, min(100, round(sum(max(0, min(100, x)) for x in parts) / len(parts))))


def _line_reg(points: list[Pivot]) -> tuple[float, float, float]:
    if len(points) < 2:
        return 0.0, points[0].price if points else 0.0, 0.0
    xs = [float(p.index) for p in points]
    ys = [p.price for p in points]
    xm = sum(xs) / len(xs)
    ym = sum(ys) / len(ys)
    denom = sum((x - xm) ** 2 for x in xs) or 1.0
    slope = sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / denom
    intercept = ym - slope * xm
    residual = mean(abs(y - (slope * x + intercept)) for x, y in zip(xs, ys))
    return slope, intercept, residual


def _slope_pct(points: list[Pivot], atr: float) -> float:
    if len(points) < 2 or atr <= 0:
        return 0.0
    slope, _, _ = _line_reg(points)
    mid = max(mean([p.price for p in points]), 1e-9)
    return slope / mid


def _trend_lines(ps: list[Pivot], candles: list[dict[str, Any]], atr: float) -> dict[str, Any] | None:
    recent = [p for p in ps if p.index >= max(0, len(candles) - 80)]
    highs = [p for p in recent if p.kind == "HIGH"][-4:]
    lows = [p for p in recent if p.kind == "LOW"][-4:]
    if len(highs) >= 2 and len(lows) >= 2:
        return {
            "high": [{"time": p.time, "price": p.price} for p in highs],
            "low": [{"time": p.time, "price": p.price} for p in lows],
            "color": "#8b78ff",
        }
    return None


def _local_prominence(candles: list[dict[str, Any]], p: Pivot, atr: float, window: int = 4) -> float:
    lo = max(0, p.index - window)
    hi = min(len(candles), p.index + window + 1)
    neighbors = candles[lo:hi]
    if p.kind == "HIGH":
        neighbor_max = max((float(c["high"]) for j, c in enumerate(neighbors) if lo + j != p.index), default=p.price)
        return max(0.0, p.price - neighbor_max) / max(atr, 1e-9)
    neighbor_min = min((float(c["low"]) for j, c in enumerate(neighbors) if lo + j != p.index), default=p.price)
    return max(0.0, neighbor_min - p.price) / max(atr, 1e-9)


def _pre_trend(candles: list[dict[str, Any]], index: int, lookback: int = 24) -> float:
    start = max(0, index - lookback)
    if index <= start:
        return 0.0
    return float(candles[index - 1]["close"]) / max(float(candles[start]["close"]), 1e-9) - 1.0


def _sequence_interleaves(highs: list[Pivot], lows: list[Pivot]) -> bool:
    merged = sorted(highs + lows, key=lambda p: p.index)
    if len(merged) < 5:
        return False
    # Require no run of 3 same-kind pivots and avoid duplicate/same-index collisions.
    for i in range(len(merged) - 2):
        if merged[i].index == merged[i + 1].index or merged[i + 1].index == merged[i + 2].index:
            return False
        if merged[i].kind == merged[i + 1].kind == merged[i + 2].kind:
            return False
    return True


def _closed_breakout(
    candles: list[dict[str, Any]],
    start_index: int,
    threshold_fn,
    direction: str,
    atr: float,
) -> int | None:
    # We treat the latest candle as potentially still forming. A breakout is only
    # considered confirmed when a closed candle (index <= n-2) closes beyond the
    # boundary and the next closed candle does not immediately reclaim it.
    n = len(candles)
    last_closed = max(start_index, n - 2)
    for j in range(start_index, last_closed + 1):
        close = float(candles[j]["close"])
        boundary = threshold_fn(j)
        if direction == "UP":
            body_out = close - boundary
            cond = body_out >= atr * 0.20
        else:
            body_out = boundary - close
            cond = body_out >= atr * 0.20
        if not cond:
            continue
        # Require one following closed candle to hold on the breakout side.
        if j + 1 > last_closed:
            continue
        nxt = float(candles[j + 1]["close"])
        next_boundary = threshold_fn(j + 1)
        hold = nxt > next_boundary if direction == "UP" else nxt < next_boundary
        if hold:
            return j
    return None


def _double(candles: list[dict[str, Any]], ps: list[Pivot], atr: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    n = len(candles)
    if n < 80 or atr <= 0 or len(ps) < 3:
        return out
    max_age = min(36, max(14, n // 8))
    for i in range(len(ps) - 2):
        a, m, b = ps[i], ps[i + 1], ps[i + 2]
        if a.kind != b.kind or a.kind == m.kind or a.index >= m.index or m.index >= b.index:
            continue
        span = b.index - a.index
        if not 12 <= span <= min(75, n // 3):
            continue
        if n - 1 - b.index > max_age:
            continue
        kind = a.kind
        name = "DOUBLE_TOP" if kind == "HIGH" else "DOUBLE_BOTTOM"
        direction = "BEARISH" if kind == "HIGH" else "BULLISH"
        # Require the reversal to occur against the prior drift.
        drift = _pre_trend(candles, a.index)
        if kind == "HIGH" and drift < 0.02:
            continue
        if kind == "LOW" and drift > -0.02:
            continue
        ref = max(abs(a.price), abs(b.price), 1e-9)
        sym = abs(a.price - b.price) / ref
        # Very tight symmetry is intentional: a double needs two comparable extrema.
        if sym > 0.0045 or abs(a.price - b.price) > atr * 0.85:
            continue
        if kind == "HIGH":
            depth = min(a.price, b.price) - m.price
            depth_req = max(atr * 2.0, ref * 0.015)
            neckline = m.price
        else:
            depth = m.price - max(a.price, b.price)
            depth_req = max(atr * 2.0, ref * 0.015)
            neckline = m.price
        if depth < depth_req:
            continue
        prom_a = _local_prominence(candles, a, atr)
        prom_b = _local_prominence(candles, b, atr)
        if min(prom_a, prom_b) < 0.30:
            continue
        left_gap = m.index - a.index
        right_gap = b.index - m.index
        gap_ratio = max(left_gap, right_gap) / max(min(left_gap, right_gap), 1)
        if gap_ratio > 1.7:
            continue
        # Do not allow a clean break of the neckline before the second pivot.
        for c in candles[m.index + 1:b.index]:
            close = float(c["close"])
            if (kind == "HIGH" and close < neckline - atr * 0.20) or (kind == "LOW" and close > neckline + atr * 0.20):
                break
        else:
            pass
        # Confirm only with a closed candle and a hold on the breakout side.
        if kind == "LOW":
            breakout = _closed_breakout(candles, b.index + 1, lambda j: neckline, "UP", atr)
        else:
            breakout = _closed_breakout(candles, b.index + 1, lambda j: neckline, "DOWN", atr)
        confirmed = breakout is not None
        # If there is a confirmed breakout, it must still be recent. For potential
        # patterns, current price must remain within the structure/under neckline.
        if confirmed and n - 1 - breakout > 12:
            continue
        if not confirmed:
            latest = float(candles[-1]["close"])
            if kind == "LOW" and latest > neckline + atr * 0.20:
                continue
            if kind == "HIGH" and latest < neckline - atr * 0.20:
                continue
        sym_score = max(0.0, 100.0 - (sym / 0.0045) * 100.0)
        depth_score = min(100.0, depth / max(depth_req * 2.0, 1e-9) * 100.0)
        prom_score = min(100.0, min(prom_a, prom_b) / 1.0 * 100.0)
        timing_score = max(0.0, 100.0 - (gap_ratio - 1.0) * 100.0)
        confirm_score = 100.0 if confirmed else 45.0
        q = quality([sym_score, depth_score, prom_score, timing_score, confirm_score])
        if q < 78:
            continue
        height = (neckline - min(a.price, b.price)) if kind == "LOW" else (max(a.price, b.price) - neckline)
        target = neckline + height if kind == "LOW" else neckline - height
        invalidation = (min(a.price, b.price) - atr * 0.25) if kind == "LOW" else (max(a.price, b.price) + atr * 0.25)
        boundary_fn = lambda _j: neckline
        lifecycle, lifecycle_detail = _recent_breakout_outcome(
            candles, breakout, boundary_fn, "UP" if kind == "LOW" else "DOWN", atr, invalidation, max_bars=12
        )
        out.append({
            "name": name,
            "direction": direction,
            "status": lifecycle if confirmed else "POTENTIAL",
            "lifecycle": lifecycle,
            "breakoutDirection": direction if breakout is not None else None,
            "quality": q,
            "points": [
                _pivot_dict(a, "LOW_1" if kind == "LOW" else "HIGH_1"),
                _pivot_dict(m, "NECKLINE"),
                _pivot_dict(b, "LOW_2" if kind == "LOW" else "HIGH_2"),
            ],
            "boundaries": {
                "a": [
                    {"time": a.time, "price": a.price},
                    {"time": m.time, "price": m.price},
                    {"time": b.time, "price": b.price},
                ],
                "b": [],
            },
            "neckline": neckline,
            "breakoutPrice": float(candles[breakout]["close"]) if breakout is not None else None,
            "breakoutTime": int(candles[breakout]["time"]) if breakout is not None else None,
            "targetPrice": target,
            "invalidationPrice": invalidation,
            "explanation": "Dua ekstrem sejenis harus rapat, swing tengah cukup dalam, konteks reversal jelas, dan CONFIRMED hanya setelah close breakout yang ditahan candle berikutnya.",
            "checks": [
                {"label": "Pivot structure", "ok": True, "detail": "ekstrem → swing tengah → ekstrem"},
                {"label": "Symmetry", "ok": True, "detail": f"selisih relatif {sym * 100:.2f}%"},
                {"label": "Depth / ATR", "ok": True, "detail": f"depth {depth:.4f} ≥ {depth_req:.4f}"},
                {"label": "Context", "ok": True, "detail": f"drift sebelum pivot {drift * 100:.1f}%"},
                {"label": "Timing", "ok": True, "detail": f"rasio jarak {gap_ratio:.2f}x"},
                {"label": "Breakout lifecycle", "ok": lifecycle in {"CONFIRMED", "HOLDING", "BREAKOUT"}, "detail": lifecycle_detail},
            ],
        })
    return out


def _flag(candles: list[dict[str, Any]], ps: list[Pivot], atr: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    n = len(candles)
    if n < 90 or atr <= 0:
        return out
    # Search only the most recent pivot pairs so the flag remains current.
    for i in range(max(0, len(ps) - 18), len(ps) - 1):
        p0 = ps[i]
        for j in range(i + 1, min(len(ps), i + 4)):
            p1 = ps[j]
            if p0.kind == p1.kind:
                continue
            pole_len = p1.index - p0.index
            impulse = abs(p1.price - p0.price)
            if not 5 <= pole_len <= 35:
                continue
            if impulse < max(4.0 * atr, max(abs(p0.price), 1e-9) * 0.02):
                continue
            bull = p0.kind == "LOW" and p1.kind == "HIGH" and p1.price > p0.price
            bear = p0.kind == "HIGH" and p1.kind == "LOW" and p1.price < p0.price
            if not (bull or bear):
                continue
            flag_ps = [p for p in ps if p.index > p1.index and p.index <= n - 2]
            highs = [p for p in flag_ps if p.kind == "HIGH"][-3:]
            lows = [p for p in flag_ps if p.kind == "LOW"][-3:]
            if len(highs) < 2 or len(lows) < 2:
                continue
            start = min(highs[0].index, lows[0].index)
            end = max(highs[-1].index, lows[-1].index)
            if end - start < 8 or n - 1 - end > 18:
                continue
            if not _sequence_interleaves(highs, lows):
                continue
            hs, hb, hr = _line_reg(highs)
            ls, lb, lr = _line_reg(lows)
            if max(hr, lr) > atr * 0.55:
                continue
            # Use scale-free slope so BTC and low-priced coins behave similarly.
            hsp = _slope_pct(highs, atr)
            lsp = _slope_pct(lows, atr)
            if bull:
                # Corrective channel slopes down and should not be a wedge.
                if not (hsp < -0.00003 and lsp < -0.00003):
                    continue
                if abs(hsp - lsp) > 0.00035:
                    continue
                name, direction = "BULLISH_FLAG", "BULLISH"
            else:
                if not (hsp > 0.00003 and lsp > 0.00003):
                    continue
                if abs(hsp - lsp) > 0.00035:
                    continue
                name, direction = "BEARISH_FLAG", "BEARISH"
            flag_high = max(p.price for p in highs)
            flag_low = min(p.price for p in lows)
            retrace = (flag_high - flag_low) / max(impulse, 1e-9)
            if not 0.10 <= retrace <= 0.45:
                continue
            # Do not permit the flag to erase most of the pole.
            pole_end_to_flag_low = (p1.price - flag_low) if bull else (flag_high - p1.price)
            if pole_end_to_flag_low / max(impulse, 1e-9) > 0.65:
                continue
            def upper_at(idx: int) -> float:
                return hs * idx + hb
            def lower_at(idx: int) -> float:
                return ls * idx + lb
            breakout = None
            last_closed = max(end, n - 2)
            for k in range(end + 1, last_closed + 1):
                c = float(candles[k]["close"])
                if bull and c >= upper_at(k) + atr * 0.20:
                    if k + 1 <= last_closed and float(candles[k + 1]["close"]) > upper_at(k + 1):
                        breakout = k
                        break
                if bear and c <= lower_at(k) - atr * 0.20:
                    if k + 1 <= last_closed and float(candles[k + 1]["close"]) < lower_at(k + 1):
                        breakout = k
                        break
            confirmed = breakout is not None
            if confirmed and n - 1 - breakout > 10:
                continue
            if not confirmed:
                latest = float(candles[-1]["close"])
                if bull and latest > upper_at(n - 1) + atr * 0.25:
                    continue
                if bear and latest < lower_at(n - 1) - atr * 0.25:
                    continue
            fit = max(0.0, 100.0 - ((hr + lr) / max(atr, 1e-9)) * 50.0)
            pole_score = min(100.0, impulse / max(atr * 8.0, 1e-9) * 100.0)
            retrace_score = max(0.0, 100.0 - abs(retrace - 0.28) * 260.0)
            conf_score = 100.0 if confirmed else 50.0
            q = quality([fit, pole_score, retrace_score, conf_score])
            if q < 76:
                continue
            base = float(candles[breakout]["close"]) if breakout is not None else float(candles[-1]["close"])
            target = base + impulse if bull else base - impulse
            invalidation = (flag_low - atr * 0.25) if bull else (flag_high + atr * 0.25)
            boundary_fn = upper_at if bull else lower_at
            lifecycle, lifecycle_detail = _recent_breakout_outcome(
                candles, breakout, boundary_fn, "UP" if bull else "DOWN", atr, invalidation, max_bars=10
            )
            out.append({
                "name": name,
                "direction": direction,
                "status": lifecycle if confirmed else "POTENTIAL",
                "lifecycle": lifecycle,
                "breakoutDirection": direction if breakout is not None else None,
                "quality": q,
                "points": [
                    _pivot_dict(p0, "POLE_START"),
                    _pivot_dict(p1, "POLE_END"),
                    _pivot_dict(highs[0], "FLAG_HIGH_1"),
                    _pivot_dict(highs[-1], "FLAG_HIGH_2"),
                    _pivot_dict(lows[0], "FLAG_LOW_1"),
                    _pivot_dict(lows[-1], "FLAG_LOW_2"),
                ],
                "boundaries": {
                    "a": [{"time": highs[0].time, "price": highs[0].price}, {"time": highs[-1].time, "price": highs[-1].price}],
                    "b": [{"time": lows[0].time, "price": lows[0].price}, {"time": lows[-1].time, "price": lows[-1].price}],
                },
                "pole": {
                    "a": {"time": p0.time, "price": p0.price},
                    "b": {"time": p1.time, "price": p1.price},
                },
                "breakoutPrice": float(candles[breakout]["close"]) if breakout is not None else None,
                "breakoutTime": int(candles[breakout]["time"]) if breakout is not None else None,
                "targetPrice": target,
                "invalidationPrice": invalidation,
                "explanation": "Pole impulsif kuat diikuti channel korektif yang melawan arah pole, dengan slope yang relatif sejajar dan confirmation hanya setelah close breakout + follow-through.",
                "checks": [
                    {"label": "Flag pole", "ok": True, "detail": f"impulse {impulse:.4f} / ATR"},
                    {"label": "Channel geometry", "ok": True, "detail": "dua boundary korektif dan hampir paralel"},
                    {"label": "Retracement", "ok": True, "detail": f"{retrace * 100:.1f}%"},
                    {"label": "Breakout lifecycle", "ok": lifecycle in {"CONFIRMED", "HOLDING", "BREAKOUT"}, "detail": lifecycle_detail},
                ],
            })
    return out



def _pattern_geometry_lifecycle(candles, upper_at, lower_at, start_idx, end_idx, direction, atr, structural_low, structural_high, breakout_buffer=0.18, max_age=12):
    """Generic closed-candle lifecycle helper for non-triangle geometries."""
    last_closed = len(candles) - 2
    breakout_idx = None
    breakout_dir = None
    for j in range(end_idx + 1, last_closed + 1):
        c = float(candles[j]["close"])
        up = upper_at(j)
        lo = lower_at(j)
        if c >= up + atr * breakout_buffer and j + 1 <= last_closed and float(candles[j + 1]["close"]) > upper_at(j + 1):
            breakout_idx, breakout_dir = j, "UP"
            break
        if c <= lo - atr * breakout_buffer and j + 1 <= last_closed and float(candles[j + 1]["close"]) < lower_at(j + 1):
            breakout_idx, breakout_dir = j, "DOWN"
            break
    actual_direction = ("BULLISH" if breakout_dir == "UP" else "BEARISH") if breakout_dir else direction
    invalidation = (structural_low - atr * 0.25) if actual_direction == "BULLISH" else (structural_high + atr * 0.25)
    boundary_fn = lower_at if actual_direction == "BULLISH" else upper_at
    lifecycle, detail = _recent_breakout_outcome(candles, breakout_idx, boundary_fn, "UP" if actual_direction == "BULLISH" else "DOWN", atr, invalidation, max_bars=max_age)
    return breakout_idx, breakout_dir, actual_direction, lifecycle, detail, invalidation


def _rectangle(candles, ps, atr):
    out=[]; n=len(candles)
    if n < 80 or atr <= 0: return out
    recent=[p for p in ps if p.index >= max(0,n-70) and p.index <= n-2]
    highs=[p for p in recent if p.kind=='HIGH'][-3:]
    lows=[p for p in recent if p.kind=='LOW'][-3:]
    if len(highs)<2 or len(lows)<2 or not _sequence_interleaves(highs,lows): return out
    merged=sorted(highs[-3:]+lows[-3:], key=lambda p:p.index)
    if merged[-1].index-merged[0].index < 12 or n-1-merged[-1].index > 14: return out
    hmin,hmax=min(p.price for p in highs),max(p.price for p in highs)
    lmin,lmax=min(p.price for p in lows),max(p.price for p in lows)
    high_span=(hmax-hmin)/max(mean([p.price for p in highs]),1e-9)
    low_span=(lmax-lmin)/max(mean([p.price for p in lows]),1e-9)
    if high_span>max(0.004,atr/max(mean([p.price for p in highs]),1e-9)*1.6): return out
    if low_span>max(0.004,atr/max(mean([p.price for p in lows]),1e-9)*1.6): return out
    upper=max(p.price for p in highs); lower=min(p.price for p in lows)
    if upper-lower < max(atr*2.5, mean([p.price for p in highs+lows])*0.006): return out
    start_idx,end_idx=merged[0].index,merged[-1].index
    upper_at=lambda i:upper; lower_at=lambda i:lower
    latest=float(candles[-1]['close'])
    breakout_idx,breakout_dir,actual,lifecycle,detail,invalidation=_pattern_geometry_lifecycle(candles,upper_at,lower_at,start_idx,end_idx,'NEUTRAL',atr,lower,upper,0.18,12)
    if breakout_idx is None and not (lower-atr*0.25 <= latest <= upper+atr*0.25): return out
    quality_score=quality([max(0,100-high_span*10000/12),max(0,100-low_span*10000/12),min(100,(end_idx-start_idx)/30*100),100 if breakout_idx else 55])
    if quality_score<70: return out
    base=float(candles[breakout_idx]['close']) if breakout_idx is not None else latest
    height=upper-lower
    target=base+height if breakout_dir=='UP' else base-height if breakout_dir=='DOWN' else None
    out.append({
        'name':'RECTANGLE','direction':actual,'structureDirection':'NEUTRAL','status':lifecycle if breakout_idx else 'POTENTIAL','lifecycle':lifecycle,'breakoutDirection':('BULLISH' if breakout_dir=='UP' else 'BEARISH') if breakout_dir else None,'quality':quality_score,
        'points':[_pivot_dict(highs[0],'HIGH_1'),_pivot_dict(highs[-1],'HIGH_2'),_pivot_dict(lows[0],'LOW_1'),_pivot_dict(lows[-1],'LOW_2')],
        'boundaries':{'a':[{'time':highs[0].time,'price':upper},{'time':highs[-1].time,'price':upper}], 'b':[{'time':lows[0].time,'price':lower},{'time':lows[-1].time,'price':lower}]},
        'breakoutPrice':float(candles[breakout_idx]['close']) if breakout_idx else None,'breakoutTime':int(candles[breakout_idx]['time']) if breakout_idx else None,'targetPrice':target,'invalidationPrice':invalidation,
        'explanation':'Harga bergerak dalam dua level horizontal yang relatif stabil; breakout hanya dihitung dari candle close + follow-through.',
        'checks':[{'label':'Horizontal boundaries','ok':True,'detail':f'high span {high_span*100:.2f}%, low span {low_span*100:.2f}%'},{'label':'Range depth','ok':True,'detail':f'range {upper-lower:.4f} / ATR'},{'label':'Breakout lifecycle','ok':lifecycle in {'CONFIRMED','HOLDING','BREAKOUT'},'detail':detail}]})
    return out


def _wedge(candles, ps, atr):
    out=[]; n=len(candles)
    if n<85 or atr<=0: return out
    recent=[p for p in ps if p.index>=max(0,n-75) and p.index<=n-2]
    highs=[p for p in recent if p.kind=='HIGH'][-3:]; lows=[p for p in recent if p.kind=='LOW'][-3:]
    if len(highs)<3 or len(lows)<3 or not _sequence_interleaves(highs,lows): return out
    hs,hb,hr=_line_reg(highs); ls,lb,lr=_line_reg(lows)
    if max(hr,lr)>atr*0.9: return out
    hchg=_triangle_line_change(highs); lchg=_triangle_line_change(lows)
    # Rising wedge = both positive with highs rising more slowly than lows; falling wedge vice versa.
    scale=max(mean([p.price for p in highs+lows]),1e-9); atr_ratio=atr/scale
    min_move=max(0.0012,atr_ratio*0.25)
    if hchg>min_move and lchg>min_move and hchg<lchg*0.88:
        name,direction='RISING_WEDGE','BEARISH'
    elif hchg<-min_move and lchg<-min_move and hchg>lchg*0.88:
        name,direction='FALLING_WEDGE','BULLISH'
    else:
        return out
    merged=sorted(highs+lows,key=lambda p:p.index); start_idx,end_idx=merged[0].index,merged[-1].index
    upper=lambda i:hs*i+hb; lower=lambda i:ls*i+lb
    start_span=upper(start_idx)-lower(start_idx); end_span=upper(end_idx)-lower(end_idx)
    if start_span<=atr*1.0 or end_span<=atr*0.15 or end_span>=start_span*0.72: return out
    if any(upper(i)<=lower(i) for i in (start_idx,(start_idx+end_idx)//2,end_idx)): return out
    inside=_triangle_inside_ratio(candles,start_idx,end_idx,upper,lower,atr)
    if inside<0.72: return out
    breakout_idx,breakout_dir,actual,lifecycle,detail,invalidation=_pattern_geometry_lifecycle(candles,upper,lower,start_idx,end_idx,direction,atr,min(p.price for p in lows),max(p.price for p in highs),0.20,12)
    if breakout_idx is None and (float(candles[-1]['close'])>upper(n-1)+atr*.3 or float(candles[-1]['close'])<lower(n-1)-atr*.3): return out
    q=quality([min(100,(1-end_span/max(start_span,1e-9))*120),inside*100,max(0,100-((hr+lr)/max(atr,1e-9))*42),100 if breakout_idx else 55])
    if q<74:return out
    height=start_span
    base=float(candles[breakout_idx]['close']) if breakout_idx else float(candles[-1]['close'])
    target=base-height if actual=='BEARISH' and breakout_idx else base+height if actual=='BULLISH' and breakout_idx else None
    out.append({'name':name,'direction':actual,'structureDirection':direction,'status':lifecycle if breakout_idx else 'POTENTIAL','lifecycle':lifecycle,'breakoutDirection':('BULLISH' if breakout_dir=='UP' else 'BEARISH') if breakout_dir else None,'quality':q,'points':[_pivot_dict(highs[0],'HIGH_1'),_pivot_dict(highs[1],'HIGH_2'),_pivot_dict(highs[2],'HIGH_3'),_pivot_dict(lows[0],'LOW_1'),_pivot_dict(lows[1],'LOW_2'),_pivot_dict(lows[2],'LOW_3')],'boundaries':{'a':[{'time':highs[0].time,'price':highs[0].price},{'time':highs[-1].time,'price':highs[-1].price}],'b':[{'time':lows[0].time,'price':lows[0].price},{'time':lows[-1].time,'price':lows[-1].price}]},'breakoutPrice':float(candles[breakout_idx]['close']) if breakout_idx else None,'breakoutTime':int(candles[breakout_idx]['time']) if breakout_idx else None,'targetPrice':target,'invalidationPrice':invalidation,'explanation':'Dua boundary miring ke arah yang sama tetapi bertemu; wedge dibedakan dari triangle berdasarkan arah kedua slope dan laju kontraksinya.','checks':[{'label':'Pivot structure','ok':True,'detail':'3 high + 3 low'}, {'label':'Convergence','ok':True,'detail':f'span {end_span:.4f} vs {start_span:.4f}'},{'label':'Wedge slope','ok':True,'detail':f'high Δ {hchg*100:.2f}%, low Δ {lchg*100:.2f}%'},{'label':'Breakout lifecycle','ok':lifecycle in {'CONFIRMED','HOLDING','BREAKOUT'},'detail':detail}]})
    return out


def _pennant(candles, ps, atr):
    out=[]; n=len(candles)
    if n<95 or atr<=0:return out
    for i in range(max(0,len(ps)-16),len(ps)-1):
        p0=ps[i]
        for j in range(i+1,min(len(ps),i+4)):
            p1=ps[j]
            if p0.kind==p1.kind: continue
            pole_len=p1.index-p0.index; impulse=abs(p1.price-p0.price)
            if not 5<=pole_len<=30: continue
            if impulse<max(4.5*atr,max(abs(p0.price),1e-9)*0.022): continue
            bull=p0.kind=='LOW' and p1.kind=='HIGH' and p1.price>p0.price
            bear=p0.kind=='HIGH' and p1.kind=='LOW' and p1.price<p0.price
            if not (bull or bear):continue
            flag_ps=[p for p in ps if p.index>p1.index and p.index<=n-2]
            highs=[p for p in flag_ps if p.kind=='HIGH'][-3:]; lows=[p for p in flag_ps if p.kind=='LOW'][-3:]
            if len(highs)<2 or len(lows)<2 or not _sequence_interleaves(highs,lows):continue
            start=min(highs[0].index,lows[0].index); end=max(highs[-1].index,lows[-1].index)
            if end-start<8 or n-1-end>16:continue
            hs,hb,hr=_line_reg(highs); ls,lb,lr=_line_reg(lows)
            if max(hr,lr)>atr*.7:continue
            hsp=_slope_pct(highs,atr); lsp=_slope_pct(lows,atr)
            if not (hsp< -0.00002 and lsp>0.00002) if bull else not (hsp>0.00002 and lsp< -0.00002): continue
            upper=lambda x:hs*x+hb; lower=lambda x:ls*x+lb
            ss=upper(start)-lower(start); es=upper(end)-lower(end)
            if ss<=atr*1.0 or es<=atr*.12 or es>=ss*.78:continue
            inside=_triangle_inside_ratio(candles,start,end,upper,lower,atr)
            if inside<.70:continue
            struct='BULLISH' if bull else 'BEARISH'; name='BULLISH_PENNANT' if bull else 'BEARISH_PENNANT'
            breakout_idx,breakout_dir,actual,lifecycle,detail,invalidation=_pattern_geometry_lifecycle(candles,upper,lower,start,end,struct,atr,min(p.price for p in lows),max(p.price for p in highs),.18,10)
            if breakout_idx is None and (float(candles[-1]['close'])>upper(n-1)+atr*.3 or float(candles[-1]['close'])<lower(n-1)-atr*.3):continue
            q=quality([inside*100,min(100,(1-es/max(ss,1e-9))*120),min(100,impulse/max(atr*8,1e-9)*100),100 if breakout_idx else 50])
            if q<74:continue
            base=float(candles[breakout_idx]['close']) if breakout_idx else float(candles[-1]['close'])
            target=base+impulse if actual=='BULLISH' and breakout_idx else base-impulse if actual=='BEARISH' and breakout_idx else None
            out.append({'name':name,'direction':actual,'structureDirection':struct,'status':lifecycle if breakout_idx else 'POTENTIAL','lifecycle':lifecycle,'breakoutDirection':('BULLISH' if breakout_dir=='UP' else 'BEARISH') if breakout_dir else None,'quality':q,'points':[_pivot_dict(p0,'POLE_START'),_pivot_dict(p1,'POLE_END'),_pivot_dict(highs[0],'PENNANT_HIGH_1'),_pivot_dict(highs[-1],'PENNANT_HIGH_2'),_pivot_dict(lows[0],'PENNANT_LOW_1'),_pivot_dict(lows[-1],'PENNANT_LOW_2')],'boundaries':{'a':[{'time':highs[0].time,'price':highs[0].price},{'time':highs[-1].time,'price':highs[-1].price}],'b':[{'time':lows[0].time,'price':lows[0].price},{'time':lows[-1].time,'price':lows[-1].price}]},'pole':{'a':{'time':p0.time,'price':p0.price},'b':{'time':p1.time,'price':p1.price}},'breakoutPrice':float(candles[breakout_idx]['close']) if breakout_idx else None,'breakoutTime':int(candles[breakout_idx]['time']) if breakout_idx else None,'targetPrice':target,'invalidationPrice':invalidation,'explanation':'Pole impulsif diikuti konsolidasi berbentuk segitiga yang menyempit; dibedakan dari flag karena kedua boundary mengarah saling bertemu.','checks':[{'label':'Pole strength','ok':True,'detail':f'persamaan impulse {impulse/atr:.1f} ATR'},{'label':'Convergence','ok':True,'detail':f'span {es:.4f} vs {ss:.4f}'},{'label':'Containment','ok':True,'detail':f'{inside*100:.0f}% inside'},{'label':'Breakout lifecycle','ok':lifecycle in {'CONFIRMED','HOLDING','BREAKOUT'},'detail':detail}]})
    return out


def _head_shoulders(candles, ps, atr, inverse=False):
    out=[]; n=len(candles)
    if n<100 or atr<=0:return out
    recent=[p for p in ps if p.index>=max(0,n-100) and p.index<=n-2]
    if not inverse:
        hs=[p for p in recent if p.kind=='HIGH'][-5:]; ls=[p for p in recent if p.kind=='LOW'][-5:]
        if len(hs)<3 or len(ls)<2:return out
        # choose last 3 highs and lows lying between them
        s1,head,s2=hs[-3:]
        mids=[p for p in ls if s1.index<p.index<s2.index]
        if len(mids)<2: mids=ls[-2:]
        n1,n2=mids[-2:]
        if not (s1.price<head.price and s2.price<head.price):return out
        shoulder_sym=abs(s1.price-s2.price)/max(head.price,1e-9)
        if shoulder_sym>.055: return out
        if head.price-max(s1.price,s2.price)<atr*1.2:return out
        neckline=mean([n1.price,n2.price])
        direction='BEARISH'; name='HEAD_AND_SHOULDERS'
        points=[_pivot_dict(s1,'LEFT_SHOULDER'),_pivot_dict(n1,'NECKLINE_1'),_pivot_dict(head,'HEAD'),_pivot_dict(n2,'NECKLINE_2'),_pivot_dict(s2,'RIGHT_SHOULDER')]
        start=min(x.index for x in [s1,n1,head,n2,s2]); end=max(x.index for x in [s1,n1,head,n2,s2])
        upper=lambda i: head.price; lower=lambda i: neckline
        breakout_idx,breakout_dir,actual,lifecycle,detail,invalidation=_pattern_geometry_lifecycle(candles,upper,lower,start,end,direction,atr,min(n1.price,n2.price),head.price,.18,12)
        latest=float(candles[-1]['close'])
        if breakout_idx is None and latest<neckline-atr*.30:breakout_dir='DOWN'
        q=quality([max(0,100-shoulder_sym*1000),min(100,(head.price-max(s1.price,s2.price))/max(atr*2,1e-9)*100),min(100,100-abs(n1.price-n2.price)/max(neckline,1e-9)*1800),100 if breakout_idx else 55])
        if q<74:return out
        base=float(candles[breakout_idx]['close']) if breakout_idx else latest
        target=base-(head.price-neckline) if (breakout_idx and breakout_dir=='DOWN') else None
        out.append({'name':name,'direction':actual,'structureDirection':direction,'status':lifecycle if breakout_idx else 'POTENTIAL','lifecycle':lifecycle,'breakoutDirection':'BEARISH' if breakout_dir=='DOWN' else 'BULLISH' if breakout_dir=='UP' else None,'quality':q,'points':points,'boundaries':{'a':[{'time':s1.time,'price':s1.price},{'time':head.time,'price':head.price},{'time':s2.time,'price':s2.price}],'b':[{'time':n1.time,'price':n1.price},{'time':n2.time,'price':n2.price}]},'neckline':neckline,'breakoutPrice':float(candles[breakout_idx]['close']) if breakout_idx else None,'breakoutTime':int(candles[breakout_idx]['time']) if breakout_idx else None,'targetPrice':target,'invalidationPrice':invalidation,'explanation':'Tiga puncak membentuk bahu kiri, kepala, dan bahu kanan dengan neckline di dua swing di antaranya.','checks':[{'label':'Shoulder symmetry','ok':True,'detail':f'{shoulder_sym*100:.2f}% berbeda'},{'label':'Head prominence','ok':True,'detail':f'{(head.price-max(s1.price,s2.price))/atr:.1f} ATR'},{'label':'Neckline','ok':True,'detail':f'{neckline:.4f}'},{'label':'Breakout lifecycle','ok':lifecycle in {'CONFIRMED','HOLDING','BREAKOUT'},'detail':detail}]})
    else:
        lows=[p for p in recent if p.kind=='LOW'][-5:]; highs=[p for p in recent if p.kind=='HIGH'][-5:]
        if len(lows)<3 or len(highs)<2:return out
        s1,head,s2=lows[-3:]
        mids=[p for p in highs if s1.index<p.index<s2.index]
        if len(mids)<2:mids=highs[-2:]
        n1,n2=mids[-2:]
        if not (s1.price>head.price and s2.price>head.price):return out
        shoulder_sym=abs(s1.price-s2.price)/max(abs(head.price),1e-9)
        if shoulder_sym>.055:return out
        if min(s1.price,s2.price)-head.price<atr*1.2:return out
        neckline=mean([n1.price,n2.price]); direction='BULLISH'; name='INVERSE_HEAD_AND_SHOULDERS'
        points=[_pivot_dict(s1,'LEFT_SHOULDER'),_pivot_dict(n1,'NECKLINE_1'),_pivot_dict(head,'HEAD'),_pivot_dict(n2,'NECKLINE_2'),_pivot_dict(s2,'RIGHT_SHOULDER')]
        start=min(x.index for x in [s1,n1,head,n2,s2]); end=max(x.index for x in [s1,n1,head,n2,s2])
        upper=lambda i:neckline; lower=lambda i:head.price
        breakout_idx,breakout_dir,actual,lifecycle,detail,invalidation=_pattern_geometry_lifecycle(candles,upper,lower,start,end,direction,atr,head.price,max(n1.price,n2.price),.18,12)
        q=quality([max(0,100-shoulder_sym*1000),min(100,(min(s1.price,s2.price)-head.price)/max(atr*2,1e-9)*100),min(100,100-abs(n1.price-n2.price)/max(neckline,1e-9)*1800),100 if breakout_idx else 55])
        if q<74:return out
        base=float(candles[breakout_idx]['close']) if breakout_idx else float(candles[-1]['close'])
        target=base+(neckline-head.price) if (breakout_idx and breakout_dir=='UP') else None
        out.append({'name':name,'direction':actual,'structureDirection':direction,'status':lifecycle if breakout_idx else 'POTENTIAL','lifecycle':lifecycle,'breakoutDirection':'BULLISH' if breakout_dir=='UP' else 'BEARISH' if breakout_dir=='DOWN' else None,'quality':q,'points':points,'boundaries':{'a':[{'time':n1.time,'price':n1.price},{'time':n2.time,'price':n2.price}],'b':[{'time':s1.time,'price':s1.price},{'time':head.time,'price':head.price},{'time':s2.time,'price':s2.price}]},'neckline':neckline,'breakoutPrice':float(candles[breakout_idx]['close']) if breakout_idx else None,'breakoutTime':int(candles[breakout_idx]['time']) if breakout_idx else None,'targetPrice':target,'invalidationPrice':invalidation,'explanation':'Tiga dasar membentuk bahu kiri, kepala, dan bahu kanan dengan neckline di dua swing di antaranya.','checks':[{'label':'Shoulder symmetry','ok':True,'detail':f'{shoulder_sym*100:.2f}% berbeda'},{'label':'Head prominence','ok':True,'detail':f'{(min(s1.price,s2.price)-head.price)/atr:.1f} ATR'},{'label':'Neckline','ok':True,'detail':f'{neckline:.4f}'},{'label':'Breakout lifecycle','ok':lifecycle in {'CONFIRMED','HOLDING','BREAKOUT'},'detail':detail}]})
    return out


def _closed_status_index(candles: list[dict[str, Any]]) -> int:
    return max(0, len(candles) - 2)


def _recent_breakout_outcome(
    candles: list[dict[str, Any]],
    breakout_idx: int | None,
    boundary_fn,
    direction: str,
    atr: float,
    invalidation_price: float,
    max_bars: int = 12,
) -> tuple[str, str]:
    """Return lifecycle and a human-readable state.

    Lifecycle is based only on CLOSED candles after the breakout. A wick does not
    confirm or invalidate a pattern. Once a breakout closes beyond the boundary,
    the next closed candle should hold that side; a reclaim through the structure
    invalidation level makes the setup FAILED/INVALIDATED.
    """
    if breakout_idx is None:
        return 'POTENTIAL', 'AWAITING BREAKOUT'
    last_closed = _closed_status_index(candles)
    if breakout_idx >= last_closed:
        return 'BREAKOUT', 'BREAKOUT CANDLE'
    age = last_closed - breakout_idx
    if age > max_bars:
        # Old confirmed patterns should not stay visually "active" forever.
        return 'HOLDING', 'BREAKOUT AGED / STILL VALID'

    for j in range(breakout_idx + 1, last_closed + 1):
        close = float(candles[j]['close'])
        b = float(boundary_fn(j))
        if direction == 'UP':
            if close <= invalidation_price:
                return 'INVALIDATED', 'BREAKOUT FAILED'
            if close < b - atr * 0.15:
                return 'FAILED', 'RECLAIMED BELOW BREAKOUT'
        else:
            if close >= invalidation_price:
                return 'INVALIDATED', 'BREAKOUT FAILED'
            if close > b + atr * 0.15:
                return 'FAILED', 'RECLAIMED ABOVE BREAKOUT'

    # One clean hold candle after breakout = confirmed. Continued closes on the
    # breakout side are labelled HOLDING so the UI can distinguish "confirmed once"
    # from "currently respecting the breakout".
    hold_count = sum(
        1 for j in range(breakout_idx + 1, last_closed + 1)
        if (float(candles[j]['close']) > float(boundary_fn(j)) if direction == 'UP'
            else float(candles[j]['close']) < float(boundary_fn(j)))
    )
    return ('HOLDING' if hold_count >= 2 else 'CONFIRMED', 'BREAKOUT HOLDING' if hold_count >= 2 else 'BREAKOUT CONFIRMED')


def _lifecycle_check(direction: str, lifecycle: str) -> tuple[bool, str]:
    if lifecycle in {'CONFIRMED', 'HOLDING'}:
        return True, 'closed breakout + follow-through'
    if lifecycle == 'BREAKOUT':
        return True, 'closed breakout detected; waiting for hold'
    if lifecycle == 'FAILED':
        return False, 'price reclaimed breakout boundary'
    if lifecycle == 'INVALIDATED':
        return False, 'price crossed structural invalidation'
    return False, 'belum ada breakout'

def _triangle_line_change(points: list[Pivot]) -> float:
    """Total fitted boundary movement from first to last pivot, normalized by price."""
    if len(points) < 2:
        return 0.0
    slope, intercept, _ = _line_reg(points)
    x0 = float(points[0].index)
    x1 = float(points[-1].index)
    y0 = slope * x0 + intercept
    y1 = slope * x1 + intercept
    mid = max(mean([p.price for p in points]), 1e-9)
    return (y1 - y0) / mid


def _triangle_touch_score(points: list[Pivot], slope: float, intercept: float, atr: float) -> float:
    if not points or atr <= 0:
        return 0.0
    errs = [abs(p.price - (slope * p.index + intercept)) for p in points]
    mean_err = mean(errs)
    return max(0.0, min(100.0, 100.0 - (mean_err / max(atr * 0.75, 1e-9)) * 100.0))


def _triangle_inside_ratio(candles: list[dict[str, Any]], start_idx: int, end_idx: int,
                           upper_fn, lower_fn, atr: float) -> float:
    if end_idx <= start_idx or atr <= 0:
        return 0.0
    total = 0
    inside = 0
    for i in range(start_idx, min(end_idx, len(candles) - 1) + 1):
        upper = upper_fn(i)
        lower = lower_fn(i)
        if not upper > lower:
            continue
        total += 1
        h = float(candles[i]["high"])
        l = float(candles[i]["low"])
        # Allow small wick excursions, but require candle bodies to remain inside.
        tol = atr * 0.45
        if h <= upper + tol and l >= lower - tol:
            inside += 1
    return inside / max(total, 1)


def _classify_triangle(highs: list[Pivot], lows: list[Pivot], atr: float) -> tuple[str, str, dict[str, float]] | None:
    """Classify triangle by fitted boundary movement, with explicit ambiguity rejection.

    The classifier intentionally prefers "unknown" over a forced label. This prevents
    wedges/channels or noisy short swings from being named as ascending/descending/
    symmetrical triangles.
    """
    if len(highs) < 2 or len(lows) < 2 or atr <= 0:
        return None

    h_change = _triangle_line_change(highs)
    l_change = _triangle_line_change(lows)
    scale = max(mean([p.price for p in highs + lows]), 1e-9)
    atr_ratio = atr / scale

    # Minimum movement must be meaningful relative to both price and noise.
    flat_tol = max(0.0007, atr_ratio * 0.12)
    move_tol = max(0.0015, atr_ratio * 0.30)
    strong_tol = max(0.0025, atr_ratio * 0.45)

    # Require actual directional movement for the non-flat side.
    if abs(h_change) <= flat_tol and l_change >= move_tol:
        name, direction = "ASCENDING_TRIANGLE", "BULLISH"
    elif h_change <= -move_tol and abs(l_change) <= flat_tol:
        name, direction = "DESCENDING_TRIANGLE", "BEARISH"
    elif h_change <= -move_tol and l_change >= move_tol:
        ratio = min(abs(h_change), abs(l_change)) / max(abs(h_change), abs(l_change), 1e-9)
        # Symmetrical should have comparable contraction rates; otherwise it can be a wedge.
        if ratio < 0.38:
            return None
        name, direction = "SYMMETRICAL_TRIANGLE", "NEUTRAL"
    else:
        return None

    return name, direction, {
        "high_change": h_change,
        "low_change": l_change,
        "flat_tol": flat_tol,
        "move_tol": move_tol,
        "strong_tol": strong_tol,
    }


def _triangle(candles: list[dict[str, Any]], ps: list[Pivot], atr: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    n = len(candles)
    if n < 90 or atr <= 0:
        return out

    recent = [p for p in ps if p.index >= max(0, n - 90) and p.index <= n - 2]
    highs_all = [p for p in recent if p.kind == "HIGH"]
    lows_all = [p for p in recent if p.kind == "LOW"]
    if len(highs_all) < 3 or len(lows_all) < 3:
        return out

    # Prefer the most recent coherent 3+3 sequence. If it overlaps too heavily,
    # try the immediately preceding block once rather than scanning arbitrary mixes.
    blocks: list[tuple[list[Pivot], list[Pivot]]] = []
    for h_slice, l_slice in [(-3, None), (-4, -1)]:
        hs = highs_all[h_slice:] if l_slice is None else highs_all[h_slice:l_slice]
        ls = lows_all[h_slice:] if l_slice is None else lows_all[h_slice:l_slice]
        if len(hs) == 3 and len(ls) == 3:
            blocks.append((hs, ls))

    seen = set()
    candidates = []
    for highs, lows in blocks:
        key = tuple((p.index, p.kind) for p in highs + lows)
        if key in seen:
            continue
        seen.add(key)
        candidates.append((highs, lows))

    for highs, lows in candidates:
        merged = sorted(highs + lows, key=lambda p: p.index)
        if len(merged) != 6 or not _sequence_interleaves(highs, lows):
            continue
        if merged[-1].index - merged[0].index < 10:
            continue
        if n - 1 - merged[-1].index > 18:
            continue

        hs, hb, hr = _line_reg(highs)
        ls, lb, lr = _line_reg(lows)
        if max(hr, lr) > atr * 0.75:
            continue

        start_idx, end_idx = merged[0].index, merged[-1].index
        upper = lambda idx: hs * idx + hb
        lower = lambda idx: ls * idx + lb
        start_span = upper(start_idx) - lower(start_idx)
        end_span = upper(end_idx) - lower(end_idx)
        if start_span <= atr * 1.20 or end_span <= atr * 0.10:
            continue
        if end_span >= start_span * 0.68:
            continue

        # Boundaries must stay ordered across the whole pattern; crossing indicates
        # a bad fit rather than a valid contracting triangle.
        sample_idxs = [start_idx, (start_idx + end_idx) // 2, end_idx]
        if any(upper(i) <= lower(i) for i in sample_idxs):
            continue

        classified = _classify_triangle(highs, lows, atr)
        if classified is None:
            continue
        name, direction, class_meta = classified

        inside_ratio = _triangle_inside_ratio(candles, start_idx, end_idx, upper, lower, atr)
        if inside_ratio < 0.78:
            continue

        high_touch = _triangle_touch_score(highs, hs, hb, atr)
        low_touch = _triangle_touch_score(lows, ls, lb, atr)
        touch_score = (high_touch + low_touch) / 2.0

        last_closed = n - 2
        breakout_idx = None
        breakout_direction = None
        for j in range(end_idx + 1, last_closed + 1):
            close = float(candles[j]["close"])
            upper_j = upper(j)
            lower_j = lower(j)
            up_ok = close >= upper_j + atr * 0.18
            down_ok = close <= lower_j - atr * 0.18
            if up_ok and j + 1 <= last_closed and float(candles[j + 1]["close"]) > upper(j + 1):
                breakout_idx, breakout_direction = j, "UP"
                break
            if down_ok and j + 1 <= last_closed and float(candles[j + 1]["close"]) < lower(j + 1):
                breakout_idx, breakout_direction = j, "DOWN"
                break

        confirmed = breakout_idx is not None
        if confirmed and n - 1 - breakout_idx > 12:
            continue

        latest = float(candles[-1]["close"])
        if not confirmed and (latest > upper(n - 1) + atr * 0.30 or latest < lower(n - 1) - atr * 0.30):
            continue

        convergence = max(0.0, min(100.0, (1.0 - end_span / max(start_span, 1e-9)) * 120.0))
        fit_score = max(0.0, min(100.0, 100.0 - ((hr + lr) / max(atr, 1e-9)) * 48.0))
        containment_score = inside_ratio * 100.0
        conf_score = 100.0 if confirmed else 45.0
        q = quality([convergence, fit_score, touch_score, containment_score, conf_score])
        if q < 78:
            continue

        actual_direction = ("BULLISH" if breakout_direction == "UP" else "BEARISH") if confirmed else direction
        breakout_price = float(candles[breakout_idx]["close"]) if breakout_idx is not None else None
        target = (breakout_price + start_span if breakout_direction == "UP" else breakout_price - start_span) if breakout_price is not None else None
        # Invalidation is anchored to the extreme structural pivot, with a small ATR
        # buffer. This keeps a bullish invalidation below the pattern and a bearish
        # invalidation above it instead of accidentally placing it above/below price.
        structural_low = min(p.price for p in lows)
        structural_high = max(p.price for p in highs)
        invalidation = (structural_low - atr * 0.25) if actual_direction == "BULLISH" else (structural_high + atr * 0.25)
        boundary_fn = lower if actual_direction == "BULLISH" else upper
        lifecycle, lifecycle_detail = _recent_breakout_outcome(
            candles, breakout_idx, boundary_fn, "UP" if actual_direction == "BULLISH" else "DOWN",
            atr, invalidation, max_bars=12
        )
        status = lifecycle if lifecycle in {"BREAKOUT", "CONFIRMED", "HOLDING", "FAILED", "INVALIDATED"} else ("POTENTIAL" if not confirmed else "CONFIRMED")
        out.append({
            "name": name,
            "direction": actual_direction,
            "status": status,
            "lifecycle": lifecycle,
            "breakoutDirection": actual_direction if breakout_idx is not None else None,
            "quality": q,
            "points": [
                _pivot_dict(highs[0], "HIGH_1"), _pivot_dict(highs[1], "HIGH_2"), _pivot_dict(highs[2], "HIGH_3"),
                _pivot_dict(lows[0], "LOW_1"), _pivot_dict(lows[1], "LOW_2"), _pivot_dict(lows[2], "LOW_3"),
            ],
            "boundaries": {
                "a": [{"time": highs[0].time, "price": highs[0].price}, {"time": highs[-1].time, "price": highs[-1].price}],
                "b": [{"time": lows[0].time, "price": lows[0].price}, {"time": lows[-1].time, "price": lows[-1].price}],
            },
            "breakoutPrice": breakout_price,
            "breakoutTime": int(candles[breakout_idx]["time"]) if breakout_idx is not None else None,
            "targetPrice": target,
            "invalidationPrice": invalidation,
            "explanation": "Triangle diklasifikasikan dari pergerakan total kedua boundary, containment candle, kualitas pivot, dan convergence. Breakout hanya diakui dari candle close, lalu lifecycle dipantau untuk hold/failure/invalidation.",
            "checks": [
                {"label": "Pivot structure", "ok": True, "detail": "3 high + 3 low yang saling bergantian"},
                {"label": "Convergence", "ok": True, "detail": f"span {end_span:.4f} vs {start_span:.4f}"},
                {"label": "Boundary fit", "ok": True, "detail": f"residual high {hr:.4f}, low {lr:.4f}"},
                {"label": "Classification", "ok": True, "detail": f"high Δ {class_meta['high_change']*100:.2f}%, low Δ {class_meta['low_change']*100:.2f}%"},
                {"label": "Candle containment", "ok": containment_score >= 78, "detail": f"{containment_score:.0f}% candle inside geometry"},
                {"label": "Breakout lifecycle", "ok": lifecycle in {"CONFIRMED", "HOLDING", "BREAKOUT"}, "detail": lifecycle_detail},
            ],
        })
    return out


def _forming_double(candles: list[dict[str, Any]], ps: list[Pivot], atr: float) -> list[dict[str, Any]]:
    """Detect an early, still-forming double top/bottom without calling it potential.
    We only require two same-type extrema with a clear intervening swing and enough
    separation/depth; breakout is intentionally *not* required here.
    """
    out: list[dict[str, Any]] = []
    n = len(candles)
    if n < 70 or atr <= 0 or len(ps) < 3:
        return out
    recent = [p for p in ps if p.index <= n - 2]
    for i in range(len(recent) - 2):
        a, m, b = recent[i], recent[i + 1], recent[i + 2]
        if a.kind != b.kind or a.kind == m.kind:
            continue
        if not (8 <= b.index - a.index <= min(60, n // 3)):
            continue
        if n - 1 - b.index > 14:
            continue
        ref = max(abs(a.price), abs(b.price), 1e-9)
        sym = abs(a.price - b.price) / ref
        if sym > 0.009 or abs(a.price - b.price) > atr * 1.5:
            continue
        if a.kind == "HIGH":
            depth = min(a.price, b.price) - m.price
            direction, name = "BEARISH", "DOUBLE_TOP"
            depth_req = max(atr * 1.25, ref * 0.008)
            neckline = m.price
        else:
            depth = m.price - max(a.price, b.price)
            direction, name = "BULLISH", "DOUBLE_BOTTOM"
            depth_req = max(atr * 1.25, ref * 0.008)
            neckline = m.price
        if depth < depth_req:
            continue
        gap_ratio = max(m.index - a.index, b.index - m.index) / max(min(m.index - a.index, b.index - m.index), 1)
        if gap_ratio > 2.25:
            continue
        prom = min(_local_prominence(candles, a, atr), _local_prominence(candles, b, atr))
        if prom < 0.12:
            continue
        # Early double only: price must still be on/inside the neckline side.
        latest = float(candles[-1]["close"])
        if a.kind == "HIGH" and latest < neckline - atr * 0.30:
            continue
        if a.kind == "LOW" and latest > neckline + atr * 0.30:
            continue
        sym_score = max(0.0, 100.0 - sym / 0.009 * 100.0)
        depth_score = min(100.0, depth / max(depth_req * 1.5, 1e-9) * 100.0)
        prom_score = min(100.0, prom / 0.8 * 100.0)
        timing_score = max(0.0, 100.0 - (gap_ratio - 1.0) * 70.0)
        q = quality([sym_score, depth_score, prom_score, timing_score])
        if q < 60:
            continue
        out.append({
            "name": name,
            "direction": direction,
            "status": "FORMING",
            "lifecycle": "FORMING",
            "quality": q,
            "points": [
                _pivot_dict(a, "LOW_1" if a.kind == "LOW" else "HIGH_1"),
                _pivot_dict(m, "NECKLINE"),
                _pivot_dict(b, "LOW_2" if a.kind == "LOW" else "HIGH_2"),
            ],
            "boundaries": {
                "a": [{"time": a.time, "price": a.price}, {"time": m.time, "price": m.price}, {"time": b.time, "price": b.price}],
                "b": [],
            },
            "neckline": neckline,
            "breakoutPrice": None,
            "breakoutTime": None,
            "targetPrice": None,
            "explanation": "Dua ekstrem dan swing tengah mulai membentuk M/W, tetapi formasi belum memenuhi seluruh syarat pattern dan belum dikonfirmasi breakout.",
            "checks": [
                {"label": "Emerging pivot structure", "ok": True, "detail": "2 ekstrem sejenis + swing tengah"},
                {"label": "Symmetry", "ok": True, "detail": f"selisih relatif {sym * 100:.2f}%"},
                {"label": "Depth / ATR", "ok": True, "detail": f"depth {depth:.4f} ≥ {depth_req:.4f}"},
                {"label": "Breakout close", "ok": False, "detail": "belum ada breakout"},
            ],
        })
    return out


def _forming_triangle(candles: list[dict[str, Any]], ps: list[Pivot], atr: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    n = len(candles)
    if n < 70 or atr <= 0:
        return out
    recent = [p for p in ps if p.index >= max(0, n - 60) and p.index <= n - 2]
    highs = [p for p in recent if p.kind == "HIGH"]
    lows = [p for p in recent if p.kind == "LOW"]
    if len(highs) < 2 or len(lows) < 2:
        return out
    hs_p = highs[-2:]
    ls_p = lows[-2:]
    merged = sorted(hs_p + ls_p, key=lambda p: p.index)
    if merged[-1].index - merged[0].index < 8 or n - 1 - merged[-1].index > 14:
        return out
    if not _sequence_interleaves(hs_p, ls_p):
        return out

    classified = _classify_triangle(hs_p, ls_p, atr)
    if classified is None:
        return out
    name, direction, class_meta = classified
    hs, hb, hr = _line_reg(hs_p)
    ls, lb, lr = _line_reg(ls_p)
    if max(hr, lr) > atr * 0.95:
        return out

    upper = lambda idx: hs * idx + hb
    lower = lambda idx: ls * idx + lb
    x0, x1 = merged[0].index, merged[-1].index
    start_span = upper(x0) - lower(x0)
    end_span = upper(x1) - lower(x1)
    if start_span <= atr * 0.65 or end_span <= atr * 0.08 or end_span >= start_span * 0.90:
        return out
    if any(upper(i) <= lower(i) for i in (x0, (x0 + x1) // 2, x1)):
        return out

    inside_ratio = _triangle_inside_ratio(candles, x0, x1, upper, lower, atr)
    if inside_ratio < 0.68:
        return out
    latest = float(candles[-1]["close"])
    if latest > upper(n - 1) + atr * 0.35 or latest < lower(n - 1) - atr * 0.35:
        return out

    high_touch = _triangle_touch_score(hs_p, hs, hb, atr)
    low_touch = _triangle_touch_score(ls_p, ls, lb, atr)
    convergence = max(0.0, min(100.0, (1.0 - end_span / max(start_span, 1e-9)) * 120.0))
    fit_score = max(0.0, min(100.0, 100.0 - ((hr + lr) / max(atr, 1e-9)) * 42.0))
    q = quality([convergence, fit_score, (high_touch + low_touch) / 2.0, inside_ratio * 100.0])
    if q < 62:
        return out

    out.append({
        "name": name,
        "direction": direction,
        "status": "FORMING",
        "lifecycle": "FORMING",
        "quality": q,
        "points": [
            _pivot_dict(hs_p[0], "HIGH_1"), _pivot_dict(hs_p[1], "HIGH_2"),
            _pivot_dict(ls_p[0], "LOW_1"), _pivot_dict(ls_p[1], "LOW_2"),
        ],
        "boundaries": {
            "a": [{"time": hs_p[0].time, "price": hs_p[0].price}, {"time": hs_p[-1].time, "price": hs_p[-1].price}],
            "b": [{"time": ls_p[0].time, "price": ls_p[0].price}, {"time": ls_p[-1].time, "price": ls_p[-1].price}],
        },
        "breakoutPrice": None,
        "breakoutTime": None,
        "targetPrice": None,
        "invalidationPrice": lower(n - 1) if direction == "BULLISH" else upper(n - 1),
        "explanation": "Struktur triangle masih berkembang. Engine hanya memberi FORMING bila dua boundary sudah mulai berkontraksi dan slope classification tidak ambigu.",
        "checks": [
            {"label": "Emerging pivot structure", "ok": True, "detail": "2 high + 2 low yang saling bergantian"},
            {"label": "Convergence", "ok": True, "detail": f"span {end_span:.4f} vs {start_span:.4f}"},
            {"label": "Classification", "ok": True, "detail": f"high Δ {class_meta['high_change']*100:.2f}%, low Δ {class_meta['low_change']*100:.2f}%"},
            {"label": "Candle containment", "ok": inside_ratio >= 0.68, "detail": f"{inside_ratio*100:.0f}% candle inside geometry"},
            {"label": "Breakout close", "ok": False, "detail": "belum ada breakout"},
        ],
    })
    return out

def _score_recency(pattern: dict[str, Any], count: int) -> int:
    indices = [int(p.get("index", count)) for p in pattern.get("points", []) if isinstance(p, dict)]
    ages = [count - idx for idx in indices]
    return max(ages) if ages else count


def detect_patterns(candles: list[dict[str, Any]], atr: float, include_forming: bool = True) -> list[dict[str, Any]]:
    """Return validated pattern candidates instead of only the single best candidate.

    This powers Pattern Finder while keeping the main chart conservative by selecting
    one best candidate in ``detect_pattern``.
    """
    c = _finite_candles(candles)
    if len(c) < 60 or atr <= 0:
        return []
    ps = pivots(c)
    strict = (_double(c, ps, atr) + _flag(c, ps, atr) + _triangle(c, ps, atr) +
              _rectangle(c, ps, atr) + _wedge(c, ps, atr) + _pennant(c, ps, atr) +
              _head_shoulders(c, ps, atr, inverse=False) + _head_shoulders(c, ps, atr, inverse=True))
    forming = (_forming_double(c, ps, atr) + _forming_triangle(c, ps, atr)) if include_forming else []
    candidates = [p for p in (strict + forming) if p.get("status") not in {"FAILED", "INVALIDATED"}]
    for candidate in candidates:
        candidate["quality"] = quality([float(candidate.get("quality", 0))])
    def key(p: dict[str, Any]) -> tuple[int, int, int]:
        status_rank = {"HOLDING": 5, "CONFIRMED": 4, "BREAKOUT": 3, "POTENTIAL": 2, "FORMING": 1}.get(str(p.get("status")), 0)
        return (status_rank, -_score_recency(p, len(c)), int(p.get("quality", 0)))
    return sorted(candidates, key=key, reverse=True)


def detect_pattern(candles: list[dict[str, Any]], atr: float) -> dict[str, Any] | None:
    candidates = detect_patterns(candles, atr, include_forming=True)
    return candidates[0] if candidates else None


def build_context(candles: list[dict[str, Any]], atr: float) -> dict[str, Any] | None:
    c = _finite_candles(candles)
    if len(c) < 20 or atr <= 0:
        return None
    return _trend_lines(pivots(c), c, atr)

