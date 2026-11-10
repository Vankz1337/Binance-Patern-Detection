# Invictus Pattern Engine

Pattern detection is deterministic. The renderer does not invent geometry.

## Required sequence

OHLCV → pivot extraction → candidate pattern → pattern-specific validation → result → renderer

## Rules

A candidate that fails a required structural check is rejected and nothing is drawn.

Quality is clipped to 0–100. It is not a probability of future price direction.

## Initial detectors

- Double Top / Double Bottom: alternating structure, symmetry, ATR depth, recentness, neckline breakout by close.
- Bull/Bear Flag: impulse pole, corrective parallel channel, slope consistency, breakout by close.
- Triangles: at least 3 highs and 3 lows, contracting range, slope classification.

The next pattern modules can be added behind the same `PatternResult` contract.


## Alpha 5 validation contract
Pattern generation is strictly upstream of rendering. The renderer does not infer a pattern from arbitrary pivots. Every candidate must pass a pattern-specific structural validator; only the selected current candidate is rendered in yellow. Trend-context lines are separate and never count as pattern geometry.

