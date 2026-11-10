export type Direction = 'BULLISH' | 'BEARISH' | 'NEUTRAL';
export type PatternStatus = 'FORMING' | 'POTENTIAL' | 'BREAKOUT' | 'CONFIRMED' | 'HOLDING' | 'FAILED' | 'INVALIDATED';
export type PatternLifecycle = 'FORMING' | 'POTENTIAL' | 'BREAKOUT' | 'HOLDING' | 'FAILED' | 'INVALIDATED';

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Pivot {
  index: number;
  time: number;
  price: number;
  kind: 'HIGH' | 'LOW';
  role?: string;
}

export interface PatternResult {
  name: string;
  direction: Direction;
  status: PatternStatus;
  quality: number;
  points: Pivot[];
  boundaries?: { a: Pivot[]; b: Pivot[] };
  pole?: { a: { time: number; price: number }; b: { time: number; price: number } };
  neckline?: number;
  breakoutPrice?: number;
  targetPrice?: number;
  invalidationPrice?: number;
  lifecycle?: PatternLifecycle;
  breakoutDirection?: Direction;
  structureDirection?: Direction;
  explanation: string;
  checks: Array<{ label: string; ok: boolean; detail: string }>;
}

export interface TrendLines {
  high: Array<{ time: number; price: number }>;
  low: Array<{ time: number; price: number }>;
  color: string;
}

export interface AnalysisResponse {
  pattern: PatternResult | null;
  structure: string;
  atr: number;
  ema20: number | null;
  ema50: number | null;
  trendLines?: TrendLines | null;
}

export interface RadarItem {
  symbol: string;
  interval: string;
  structure: string;
  priority: number;
  pattern: PatternResult | null;
  error?: string;
}

export interface RadarResponse {
  items: RadarItem[];
  updatedAt: number;
}


export interface PatternFinderMatch {
  symbol: string;
  interval: string;
  pattern: PatternResult;
  match: number;
  price: number;
  status: string;
  signals: number;
}

export interface PatternFinderResponse {
  pattern: string;
  patternLabel: string;
  interval: string;
  sensitivity: string;
  scanned: number;
  matches: PatternFinderMatch[];
  updatedAt: number;
}

