import type { AnalysisResponse, Candle, RadarResponse, PatternFinderResponse } from './types';

const API = import.meta.env.VITE_API_BASE ?? '/api';
const BINANCE_ENDPOINTS = [
  'https://data-api.binance.vision/api/v3/klines',
  'https://api-gcp.binance.com/api/v3/klines',
  'https://api.binance.com/api/v3/klines',
];

async function requestJson<T>(url: string, init?: RequestInit, timeoutMs = 12000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      ...init,
      signal: controller.signal,
      headers: { Accept: 'application/json', ...(init?.headers ?? {}) },
      cache: 'no-store',
    });
    const text = await response.text();
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${text.slice(0, 240)}`);
    return JSON.parse(text) as T;
  } finally {
    window.clearTimeout(timeout);
  }
}

function mapKlines(rows: unknown): Candle[] {
  if (!Array.isArray(rows)) throw new Error('Binance returned an invalid candle payload');
  const cleaned = rows.map((r: any) => ({
    time: Math.floor(Number(r[0]) / 1000),
    open: Number(r[1]),
    high: Number(r[2]),
    low: Number(r[3]),
    close: Number(r[4]),
    volume: Number(r[5]),
  })).filter((c) => Number.isFinite(c.time) && c.time > 0 &&
                    [c.open,c.high,c.low,c.close,c.volume].every(Number.isFinite));
  cleaned.sort((a, b) => a.time - b.time);
  const unique: Candle[] = [];
  for (const c of cleaned) {
    const last = unique[unique.length - 1];
    if (last && last.time === c.time) unique[unique.length - 1] = c;
    else if (!last || c.time > last.time) unique.push(c);
  }
  return unique;
}

export async function getCandles(symbol: string, interval: string, limit = 300): Promise<Candle[]> {
  const qs = `?symbol=${encodeURIComponent(symbol.toUpperCase())}&interval=${encodeURIComponent(interval)}&limit=${limit}`;
  // Backend first. If it is unavailable, use Binance directly for the chart.
  // This means the chart can still render while the Python analysis service is offline.
  try {
    const data = await requestJson<Candle[]>(`${API}/market/klines${qs}`);
    if (data.length) return data;
  } catch (backendError) {
    console.warn('Backend market-data request failed; trying Binance directly.', backendError);
  }
  let lastError: unknown = null;
  for (const endpoint of BINANCE_ENDPOINTS) {
    try {
      return mapKlines(await requestJson<unknown>(`${endpoint}${qs}`, undefined, 10000));
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError instanceof Error ? lastError : new Error('All Binance public market-data endpoints failed');
}

export async function analyze(symbol: string, interval: string, limit = 300): Promise<AnalysisResponse> {
  return requestJson<AnalysisResponse>(`${API}/analysis?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&limit=${limit}`);
}

export async function health() {
  return requestJson<{ ok: boolean; service: string; version: string }>(`${API}/health`);
}

export { API };

export async function radar(): Promise<RadarResponse> {
  return requestJson<RadarResponse>(`${API}/radar`, undefined, 30000);
}


export async function patternFinder(pattern: string, interval: string, sensitivity: string, universe: number): Promise<PatternFinderResponse> {
  const qs = new URLSearchParams({ pattern, interval, sensitivity, universe: String(universe) });
  return requestJson<PatternFinderResponse>(`${API}/pattern-finder?${qs.toString()}`, undefined, 120000);
}

