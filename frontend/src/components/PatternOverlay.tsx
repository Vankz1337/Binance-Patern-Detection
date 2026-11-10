import type { PatternResult } from '../types';
interface Props { pattern: PatternResult | null; }
export function PatternOverlay({ pattern }: Props) {
  if (!pattern) return <div className="pattern-empty">NO VALID PATTERN</div>;
  return <div className="pattern-card" data-direction={pattern.direction} data-status={pattern.status}>
    <div className="pattern-title">{pattern.name.replaceAll('_',' ')}</div>
    <div className="pattern-meta"><span>{pattern.structureDirection ?? pattern.direction}</span>{pattern.breakoutDirection && <span>BREAKOUT: {pattern.breakoutDirection}</span>}<span>{pattern.lifecycle ?? pattern.status}</span><span>{pattern.quality}/100</span></div>
    {(pattern.targetPrice != null || pattern.invalidationPrice != null) && <div className="pattern-levels">{pattern.targetPrice != null && <span>T {pattern.targetPrice.toFixed(2)}</span>}{pattern.invalidationPrice != null && <span>I {pattern.invalidationPrice.toFixed(2)}</span>}</div>}
  </div>;
}

