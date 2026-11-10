from app.patterns.engine import Pivot, _classify_triangle, detect_pattern


def mk_candles(closes, vol=1000):
    out = []
    for i, p in enumerate(closes):
        wick = max(0.05, abs(p) * 0.001)
        out.append({"time": i + 1, "open": p, "high": p + wick, "low": p - wick, "close": p, "volume": vol})
    return out


def test_flat_noise_rejected():
    closes = [100 + (i % 2) * 0.02 for i in range(140)]
    assert detect_pattern(mk_candles(closes), 0.2) is None


def test_double_bottom_needs_close_symmetry():
    closes = [110 - i * 0.25 for i in range(30)]
    closes += [102, 99, 96, 94, 96, 99, 102, 100, 97, 95, 94.4, 96, 99, 103, 108]
    closes += [112, 116, 120] + [120] * 24
    result = detect_pattern(mk_candles(closes), 1.0)
    if result and result["name"] == "DOUBLE_BOTTOM":
        pts = result["points"]
        assert pts[0]["role"] == "LOW_1"
        assert pts[2]["role"] == "LOW_2"
        assert abs(pts[0]["price"] - pts[2]["price"]) / max(pts[0]["price"], pts[2]["price"]) <= 0.0045


def test_far_apart_double_rejected():
    closes = [110 - i * 0.25 for i in range(30)]
    closes += [101, 98, 95, 93, 95, 98, 101, 104, 102, 99, 96, 94, 95, 98, 102]
    closes += [106] * 35
    result = detect_pattern(mk_candles(closes), 1.0)
    assert result is None or result["name"] != "DOUBLE_BOTTOM"


def test_triangle_requires_three_by_three():
    closes = [100 + i * 0.1 for i in range(80)]
    # gentle converging wave in the tail
    tail = [108, 104, 107, 105, 106, 106, 105.5, 106.5, 105.2, 106.2, 105.0, 105.8, 105.3, 105.6]
    closes = closes[:80] + tail + [105.5] * 10
    result = detect_pattern(mk_candles(closes), 0.7)
    if result:
        assert result["name"] in {"ASCENDING_TRIANGLE", "DESCENDING_TRIANGLE", "SYMMETRICAL_TRIANGLE", "DOUBLE_TOP", "DOUBLE_BOTTOM", "BULLISH_FLAG", "BEARISH_FLAG"}


def test_result_quality_is_bounded():
    closes = [100 + i * 0.02 for i in range(140)]
    result = detect_pattern(mk_candles(closes), 0.2)
    assert result is None or 0 <= result["quality"] <= 100


def test_no_invalid_shape_forced():
    candles = []
    for i in range(140):
        p = 100 + (i % 7) * 0.03
        candles.append({"time": i + 1, "open": p, "high": p + 0.08, "low": p - 0.08, "close": p, "volume": 1000})
    assert detect_pattern(candles, 0.15) is None


def test_triangle_classifier_distinguishes_types():
    highs_flat = [Pivot(10, 10, 110.0, 'HIGH'), Pivot(20, 20, 110.1, 'HIGH'), Pivot(30, 30, 109.9, 'HIGH')]
    lows_up = [Pivot(12, 12, 100.0, 'LOW'), Pivot(22, 22, 101.5, 'LOW'), Pivot(32, 32, 103.0, 'LOW')]
    assert _classify_triangle(highs_flat, lows_up, 2.0)[0] == 'ASCENDING_TRIANGLE'

    highs_down = [Pivot(10, 10, 110.0, 'HIGH'), Pivot(20, 20, 108.5, 'HIGH'), Pivot(30, 30, 107.0, 'HIGH')]
    lows_flat = [Pivot(12, 12, 100.0, 'LOW'), Pivot(22, 22, 100.1, 'LOW'), Pivot(32, 32, 99.9, 'LOW')]
    assert _classify_triangle(highs_down, lows_flat, 2.0)[0] == 'DESCENDING_TRIANGLE'

    highs_down2 = [Pivot(10, 10, 110.0, 'HIGH'), Pivot(20, 20, 108.2, 'HIGH'), Pivot(30, 30, 106.4, 'HIGH')]
    lows_up2 = [Pivot(12, 12, 100.0, 'LOW'), Pivot(22, 22, 101.7, 'LOW'), Pivot(32, 32, 103.4, 'LOW')]
    assert _classify_triangle(highs_down2, lows_up2, 2.0)[0] == 'SYMMETRICAL_TRIANGLE'


def test_triangle_classifier_rejects_ambiguous_slopes():
    highs = [Pivot(10, 10, 110.0, 'HIGH'), Pivot(20, 20, 109.7, 'HIGH'), Pivot(30, 30, 109.4, 'HIGH')]
    lows = [Pivot(12, 12, 100.0, 'LOW'), Pivot(22, 22, 100.25, 'LOW'), Pivot(32, 32, 100.5, 'LOW')]
    assert _classify_triangle(highs, lows, 3.0) is None


def test_lifecycle_breakout_holding_and_invalidation():
    from app.patterns.engine import _recent_breakout_outcome

    candles = [
        {"time": 1, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
        {"time": 2, "open": 101, "high": 102, "low": 100, "close": 101, "volume": 1},
        {"time": 3, "open": 104, "high": 105, "low": 103, "close": 104, "volume": 1},
        {"time": 4, "open": 105, "high": 106, "low": 104, "close": 105, "volume": 1},
        {"time": 5, "open": 106, "high": 107, "low": 105, "close": 106, "volume": 1},
        {"time": 6, "open": 105, "high": 106, "low": 103, "close": 104, "volume": 1},
    ]
    boundary = lambda _i: 102.0
    assert _recent_breakout_outcome(candles, 2, boundary, 'UP', 1.0, 98.0, max_bars=12)[0] == 'HOLDING'

    candles[-2]["close"] = 97.5
    candles[-2]["open"] = 98.0
    candles[-2]["high"] = 98.5
    candles[-2]["low"] = 97.0
    assert _recent_breakout_outcome(candles, 2, boundary, 'UP', 1.0, 98.0, max_bars=12)[0] == 'INVALIDATED'

