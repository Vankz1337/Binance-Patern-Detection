import { useEffect, useRef } from 'react';
import { ColorType, LineStyle, createChart } from 'lightweight-charts';
import type { Candle, PatternResult, TrendLines } from '../types';

interface Props {
  candles: Candle[];
  pattern: PatternResult | null;
  showVolume: boolean;
  trendLines?: TrendLines | null;
  showAutoTrend?: boolean;
  viewKey: string;
}

type Series = any;

function normalizeCandles(input: Candle[]): Candle[] {
  const rows = input
    .filter((c) => [c.time, c.open, c.high, c.low, c.close, c.volume].every(Number.isFinite))
    .map((c) => ({ ...c, time: Math.floor(c.time) }));
  rows.sort((a, b) => a.time - b.time);
  const out: Candle[] = [];
  for (const c of rows) {
    const last = out[out.length - 1];
    if (last && last.time === c.time) out[out.length - 1] = c;
    else if (!last || c.time > last.time) out.push(c);
  }
  return out;
}

function emaSeries(candles: Candle[], period: number) {
  if (!candles.length) return [];
  const k = 2 / (period + 1);
  let prev = candles[0].close;
  return candles.map((c, i) => {
    prev = i === 0 ? c.close : c.close * k + prev * (1 - k);
    return { time: c.time as any, value: prev };
  });
}

function linePoints(points: Array<{ time: number; price: number }>) {
  const sorted = [...points]
    .map((p) => ({ time: Math.floor(p.time) as any, value: Number(p.price) }))
    .filter((p) => Number.isFinite(p.time) && Number.isFinite(p.value))
    .sort((a, b) => Number(a.time) - Number(b.time));
  const out: typeof sorted = [];
  for (const p of sorted) {
    if (out.length && Number(out[out.length - 1].time) === Number(p.time)) out[out.length - 1] = p;
    else out.push(p);
  }
  return out;
}

export function TradingChart({ candles, pattern, showVolume, trendLines, viewKey, showAutoTrend = true }: Props) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const candleRef = useRef<Series>(null);
  const volumeRef = useRef<Series>(null);
  const ema20Ref = useRef<Series>(null);
  const ema50Ref = useRef<Series>(null);
  const patternARef = useRef<Series>(null);
  const patternBRef = useRef<Series>(null);
  const necklineRef = useRef<Series>(null);
  const poleRef = useRef<Series>(null);
  const trendHighRef = useRef<Series>(null);
  const trendLowRef = useRef<Series>(null);
  const resizeRef = useRef<ResizeObserver | null>(null);
  const previousViewKeyRef = useRef(viewKey);

  useEffect(() => {
    if (!rootRef.current) return;
    const root = rootRef.current;
    const chart = createChart(root, {
      layout: { background: { type: ColorType.Solid, color: '#090710' }, textColor: '#a9a4b8' },
      grid: { vertLines: { color: '#171323' }, horzLines: { color: '#171323' } },
      rightPriceScale: { borderColor: '#2a2340' },
      timeScale: { borderColor: '#2a2340', rightOffset: 4, fixLeftEdge: false },
      crosshair: { mode: 1 },
      width: Math.max(root.clientWidth, 320),
      height: Math.max(root.clientHeight, 460),
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
    });

    const candle = chart.addCandlestickSeries({
      upColor: '#48e3a8', downColor: '#ff5e88', borderVisible: false,
      wickUpColor: '#48e3a8', wickDownColor: '#ff5e88',
    });
    const volume = chart.addHistogramSeries({
      priceFormat: { type: 'volume' }, priceScaleId: '', lastValueVisible: false, priceLineVisible: false,
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
    const ema20 = chart.addLineSeries({ color: '#d4b7ff', lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    const ema50 = chart.addLineSeries({ color: '#8057ff', lineWidth: 2, priceLineVisible: false, lastValueVisible: false });

    const patternA = chart.addLineSeries({ color: '#ffd54a', lineWidth: 3, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
    const patternB = chart.addLineSeries({ color: '#ffd54a', lineWidth: 3, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
    const neckline = chart.addLineSeries({ color: '#ffd54a', lineWidth: 2, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
    const pole = chart.addLineSeries({ color: '#ffd54a', lineWidth: 3, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
    const trendHigh = chart.addLineSeries({ color: '#8b78ff', lineWidth: 2, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });
    const trendLow = chart.addLineSeries({ color: '#8b78ff', lineWidth: 2, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false });

    candleRef.current = candle;
    volumeRef.current = volume;
    ema20Ref.current = ema20;
    ema50Ref.current = ema50;
    patternARef.current = patternA;
    patternBRef.current = patternB;
    necklineRef.current = neckline;
    poleRef.current = pole;
    trendHighRef.current = trendHigh;
    trendLowRef.current = trendLow;
    chartRef.current = chart;

    const resize = new ResizeObserver(() => {
      chart.resize(Math.max(root.clientWidth, 320), Math.max(root.clientHeight, 460));
    });
    resize.observe(root);
    resizeRef.current = resize;

    return () => {
      resize.disconnect();
      resizeRef.current = null;
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
      ema20Ref.current = null;
      ema50Ref.current = null;
      patternARef.current = null;
      patternBRef.current = null;
      necklineRef.current = null;
      poleRef.current = null;
      trendHighRef.current = null;
      trendLowRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    const candle = candleRef.current;
    const volume = volumeRef.current;
    if (!chart || !candle || !volume) return;

    const data = normalizeCandles(candles);
    if (!data.length) {
      candle.setData([]);
      volume.setData([]);
      return;
    }

    candle.setData(data.map((c) => ({ time: c.time as any, open: c.open, high: c.high, low: c.low, close: c.close })));
    volume.setData(data.map((c) => ({ time: c.time as any, value: c.volume, color: c.close >= c.open ? '#28b884' : '#9e3e60' })));
    ema20Ref.current?.setData(emaSeries(data, 20));
    ema50Ref.current?.setData(emaSeries(data, 50));

    if (previousViewKeyRef.current !== viewKey || previousViewKeyRef.current === viewKey && chart.timeScale().getVisibleLogicalRange() == null) {
      chart.timeScale().fitContent();
      previousViewKeyRef.current = viewKey;
    }
  }, [candles, viewKey]);

  useEffect(() => {
    const candle = candleRef.current;
    const a = patternARef.current;
    const b = patternBRef.current;
    const neckline = necklineRef.current;
    const pole = poleRef.current;
    const th = trendHighRef.current;
    const tl = trendLowRef.current;
    if (!candle || !a || !b || !neckline || !pole || !th || !tl) return;

    candle.setMarkers([]);
    a.setData([]);
    b.setData([]);
    neckline.setData([]);
    pole.setData([]);
    th.setData(showAutoTrend ? linePoints(trendLines?.high ?? []) : []);
    tl.setData(showAutoTrend ? linePoints(trendLines?.low ?? []) : []);

    if (!pattern) return;

    const isDouble = pattern.name === 'DOUBLE_TOP' || pattern.name === 'DOUBLE_BOTTOM';
    // Lightweight Charts requires markers to be strictly ordered by time.
    // Pattern engines can return pivots grouped by role (e.g. pole, highs, lows),
    // so normalize the marker stream independently from pattern geometry.
    const markerPoints = [...pattern.points]
      .map((p) => ({ ...p, time: Math.floor(Number(p.time)) }))
      .filter((p) => Number.isFinite(p.time) && Number.isFinite(p.price))
      .sort((a, b) => a.time - b.time);

    const uniqueMarkerPoints = markerPoints.filter((p, i, arr) =>
      i === 0 || p.time !== arr[i - 1].time
    );

    // Clean chart labels: show only the pivots that define the visible pattern.
    // Extra validation pivots remain in the API but are intentionally not painted
    // as large marker labels, preventing the H1/H2/H3/L1/L2/L3 stack seen before.
    let displayPoints = uniqueMarkerPoints;
    if (pattern.name === 'SYMMETRICAL_TRIANGLE' || pattern.name === 'ASCENDING_TRIANGLE' || pattern.name === 'DESCENDING_TRIANGLE') {
      const highs = uniqueMarkerPoints.filter((p) => p.kind === 'HIGH');
      const lows = uniqueMarkerPoints.filter((p) => p.kind === 'LOW');
      displayPoints = [...highs.slice(0, 1), ...highs.slice(-1), ...lows.slice(0, 1), ...lows.slice(-1)];
      displayPoints.sort((a, b) => a.time - b.time);
    } else if (pattern.name === 'BULLISH_FLAG' || pattern.name === 'BEARISH_FLAG' || pattern.name === 'BULLISH_PENNANT' || pattern.name === 'BEARISH_PENNANT') {
      const pole = uniqueMarkerPoints.filter((p) => p.role === 'POLE_START' || p.role === 'POLE_END');
      const highs = uniqueMarkerPoints.filter((p) => p.role?.startsWith('FLAG_HIGH') || p.role?.startsWith('PENNANT_HIGH'));
      const lows = uniqueMarkerPoints.filter((p) => p.role?.startsWith('FLAG_LOW') || p.role?.startsWith('PENNANT_LOW'));
      displayPoints = [...pole, ...highs.slice(0, 1), ...highs.slice(-1), ...lows.slice(0, 1), ...lows.slice(-1)];
      displayPoints.sort((a, b) => a.time - b.time);
    }

    candle.setMarkers(displayPoints.map((p, i) => ({
      time: p.time as any,
      position: p.kind === 'LOW' ? 'belowBar' : 'aboveBar',
      color: '#ffd54a',
      shape: p.kind === 'LOW' ? 'arrowUp' : 'arrowDown',
      text: p.role ?? (isDouble ? String(i + 1) : ''),
    })));

    const lifecycle = pattern.lifecycle ?? pattern.status;
    const isForming = lifecycle === 'FORMING';
    const isFailed = lifecycle === 'FAILED' || lifecycle === 'INVALIDATED';
    const geometryStyle = isForming || isFailed ? LineStyle.Dashed : LineStyle.Solid;
    const geometryColor = isFailed ? '#ff5e88' : '#ffd54a';
    a.applyOptions({ color: geometryColor, lineStyle: geometryStyle, lineWidth: isForming ? 2 : 3 });
    b.applyOptions({ color: geometryColor, lineStyle: geometryStyle, lineWidth: isForming ? 2 : 3 });
    pole.applyOptions({ color: geometryColor, lineStyle: geometryStyle, lineWidth: isForming ? 2 : 3 });
    neckline.applyOptions({ color: geometryColor });
    neckline.applyOptions({ lineStyle: LineStyle.Dashed, lineWidth: 2 });

    const boundaries = pattern.boundaries;
    if (pattern.pole && !isForming) {
      pole.setData(linePoints([
        pattern.pole.a,
        pattern.pole.b,
      ]));
    }
    if (boundaries?.a?.length) {
      a.setData(linePoints(boundaries.a));
    }
    if (boundaries?.b?.length) {
      b.setData(linePoints(boundaries.b));
    }

    if (isDouble && pattern.points.length >= 3 && pattern.neckline != null) {
      const times = pattern.points.map((p) => p.time).sort((x, y) => x - y);
      neckline.setData(linePoints([
        { time: times[0], price: pattern.neckline },
        { time: times[times.length - 1], price: pattern.neckline },
      ]));
    }
  }, [pattern, trendLines, showAutoTrend]);

  useEffect(() => {
    volumeRef.current?.applyOptions({ visible: showVolume });
  }, [showVolume]);

  return <div ref={rootRef} className="chart-root" />;
}

