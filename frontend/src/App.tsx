import { useEffect, useMemo, useRef, useState } from 'react';
import { analyze, getCandles, health, radar as fetchRadar, patternFinder } from './api';
import { TradingChart } from './components/TradingChart';
import { PatternOverlay } from './components/PatternOverlay';
import type { AnalysisResponse, Candle, PatternFinderMatch, PatternResult, RadarItem } from './types';
import './styles.css';

const COINS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT'];
const TFS = ['1m', '5m', '15m', '1h', '4h', '1d'];
const STAGES = ['1d', '4h', '1h', '15m'];
const PATTERNS = [
  ['BULLISH_FLAG','Bull Flag','BULLISH'], ['BEARISH_FLAG','Bear Flag','BEARISH'],
  ['DOUBLE_BOTTOM','Double Bottom (W)','BULLISH'], ['DOUBLE_TOP','Double Top (M)','BEARISH'],
  ['HEAD_AND_SHOULDERS','Head & Shoulders','BEARISH'], ['INVERSE_HEAD_AND_SHOULDERS','Inverse H&S','BULLISH'],
  ['ASCENDING_TRIANGLE','Ascending Triangle','BULLISH'], ['DESCENDING_TRIANGLE','Descending Triangle','BEARISH'],
  ['SYMMETRICAL_TRIANGLE','Symmetrical Triangle','NEUTRAL'], ['FALLING_WEDGE','Falling Wedge','BULLISH'],
  ['RISING_WEDGE','Rising Wedge','BEARISH'], ['BULLISH_PENNANT','Bullish Pennant','BULLISH'],
  ['BEARISH_PENNANT','Bearish Pennant','BEARISH'], ['RECTANGLE','Rectangle','NEUTRAL'],
] as const;

type View = 'dashboard' | 'finder' | 'scanner';

function patternLabel(p: PatternResult | null) { return p ? `${p.name.replaceAll('_',' ')} • ${p.status}` : 'NO ACTIVE PATTERN'; }
function tone(direction?: string) { return direction === 'BULLISH' ? 'bull' : direction === 'BEARISH' ? 'bear' : 'neutral'; }

export default function App() {
  const [view, setView] = useState<View>('dashboard');
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [interval, setInterval] = useState('1d');
  const [candles, setCandles] = useState<Candle[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [showVolume, setShowVolume] = useState(true);
  const [showAutoTrend, setShowAutoTrend] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [backendOk, setBackendOk] = useState(false);
  const [radarItems, setRadarItems] = useState<RadarItem[]>([]);
  const [radarLoading, setRadarLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [finderPattern, setFinderPattern] = useState('BULLISH_FLAG');
  const [finderTF, setFinderTF] = useState('1d');
  const [finderSensitivity, setFinderSensitivity] = useState('balanced');
  const [finderUniverse, setFinderUniverse] = useState(250);
  const [finderLoading, setFinderLoading] = useState(false);
  const [finderResults, setFinderResults] = useState<PatternFinderMatch[]>([]);
  const [finderMeta, setFinderMeta] = useState<{scanned:number; patternLabel:string; updatedAt:number}|null>(null);
  const [finderError, setFinderError] = useState<string|null>(null);
  const previousAlerts = useRef(new Map<string,string>());
  const audioCtx = useRef<AudioContext|null>(null);

  useEffect(() => {
    if (view !== 'dashboard') return;
    let cancelled = false;
    setLoading(true); setError(null); setAnalysisError(null); setAnalysis(null);
    getCandles(symbol, interval).then(d=>{if(!cancelled)setCandles(d)}).catch(e=>{if(!cancelled){setCandles([]);setError(e instanceof Error?e.message:String(e))}}).finally(()=>{if(!cancelled)setLoading(false)});
    analyze(symbol, interval).then(r=>{if(!cancelled)setAnalysis(r)}).catch(e=>{if(!cancelled)setAnalysisError(e instanceof Error?e.message:String(e))});
    return ()=>{cancelled=true};
  },[symbol,interval,view]);

  useEffect(()=>{health().then(r=>setBackendOk(Boolean(r.ok))).catch(()=>setBackendOk(false))},[]);
  useEffect(()=>{ let alive=true; const refresh=async()=>{setRadarLoading(true);try{const r=await fetchRadar();if(alive)setRadarItems(r.items??[])}catch{}finally{if(alive)setRadarLoading(false)}}; refresh(); const id=window.setInterval(refresh,45000); return()=>{alive=false;window.clearInterval(id)}} ,[]);

  useEffect(()=>{
    if(!radarItems.length)return;
    const interacted=!!audioCtx.current;
    radarItems.forEach(item=>{const p=item.pattern;if(!p)return;const key=`${item.symbol}:${item.interval}`;const state=`${p.name}:${p.lifecycle??p.status}:${p.quality}`;const prev=previousAlerts.current.get(key);previousAlerts.current.set(key,state);if(prev===state)return;const msg=`${item.symbol} ${item.interval}: ${p.name.replaceAll('_',' ')} ${p.lifecycle??p.status}`;try{if('Notification'in window&&Notification.permission==='granted')new Notification('INVICTUS Pattern Alert',{body:msg})}catch{};window.dispatchEvent(new CustomEvent('invictus-alert',{detail:msg}));if(interacted)try{const ctx=audioCtx.current!;const o=ctx.createOscillator(),g=ctx.createGain();o.frequency.value=p.status==='CONFIRMED'?880:620;g.gain.value=.05;o.connect(g);g.connect(ctx.destination);o.start();o.stop(ctx.currentTime+.18)}catch{}})
  },[radarItems]);

  useEffect(()=>{const unlock=()=>{if(!audioCtx.current){try{audioCtx.current=new AudioContext()}catch{}}if('Notification'in window&&Notification.permission==='default')Notification.requestPermission().catch(()=>{});window.removeEventListener('pointerdown',unlock)};window.addEventListener('pointerdown',unlock,{once:true});return()=>window.removeEventListener('pointerdown',unlock)},[]);

  const radarByCoin=useMemo(()=>{const map=new Map<string,RadarItem[]>();for(const i of radarItems){if(!map.has(i.symbol))map.set(i.symbol,[]);map.get(i.symbol)!.push(i)}return COINS.map(c=>{const items=(map.get(c)??[]).sort((a,b)=>(b.priority-a.priority)||((b.pattern?.quality??0)-(a.pattern?.quality??0)));const active=items.find(x=>x.pattern&&!['FAILED','INVALIDATED'].includes(x.pattern.lifecycle??x.pattern.status))??null;return{symbol:c,items,active,priority:active?active.priority:0}}).sort((a,b)=>b.priority-a.priority||(b.active?.pattern?.quality??0)-(a.active?.pattern?.quality??0))},[radarItems]);
  const filteredRadar=useMemo(()=>{const q=search.trim().toUpperCase();return q?radarByCoin.filter(r=>r.symbol.includes(q)||r.active?.pattern?.name.includes(q.replaceAll(' ','_'))):radarByCoin},[radarByCoin,search]);

  async function runFinder(){setFinderLoading(true);setFinderError(null);setFinderResults([]);setFinderMeta(null);try{const r=await patternFinder(finderPattern,finderTF,finderSensitivity,finderUniverse);setFinderResults(r.matches);setFinderMeta({scanned:r.scanned,patternLabel:r.patternLabel,updatedAt:r.updatedAt})}catch(e){setFinderError(e instanceof Error?e.message:String(e))}finally{setFinderLoading(false)}}
  function openMatch(m:PatternFinderMatch){setSymbol(m.symbol);setInterval(m.interval);setView('dashboard')}
  const last=candles.at(-1);
  const title=symbol.replace('USDT','');

  return <div className="app-shell">
    <header className="topbar"><div className="brand"><div className="brand-icon">I</div><strong>INVICTUS</strong></div><nav><button className={view==='dashboard'?'nav-btn active':''} onClick={()=>setView('dashboard')}>Dashboard</button><button className={view==='finder'?'nav-btn active':''} onClick={()=>setView('finder')}>Pattern Finder</button><button className={view==='scanner'?'nav-btn active':''} onClick={()=>setView('scanner')}>Live Scanner</button><button className="nav-btn">Market Analysis</button><button className="nav-btn">Backtest</button></nav><div className="live"><i/> BINANCE SPOT • LIVE</div></header>
    <div className="ticker">{COINS.map(c=><button key={c} className={c===symbol?'active':''} onClick={()=>{setSymbol(c);setView('dashboard')}}>{c.replace('USDT','')} <small>USDT</small></button>)}</div>
    {view==='finder' ? <PatternFinderPage {...{finderPattern,setFinderPattern,finderTF,setFinderTF,finderSensitivity,setFinderSensitivity,finderUniverse,setFinderUniverse,finderLoading,finderResults,finderMeta,finderError,runFinder,openMatch}}/> : view==='scanner' ? <LiveScannerPage radarItems={radarItems} loading={radarLoading} onOpen={(i)=>{setSymbol(i.symbol);setInterval(i.interval);setView('dashboard')}}/> : <main className="workspace">
      <aside className="left-panel card"><div className="section-title">Coin List <span>LIVE</span></div><input className="search" placeholder="Cari coin..." value={search} onChange={e=>setSearch(e.target.value)}/><div className="radar-note">{radarLoading?'Scanning 36 market/timeframe cells…':'Auto scan • 6 coins × 6 timeframes'}</div><div className="coin-list">{filteredRadar.map(row=><button key={row.symbol} onClick={()=>setSymbol(row.symbol)} className={row.symbol===symbol?'coin selected':'coin'}><div className="coin-head"><b>{row.symbol}</b><span className={`priority p${row.priority}`}>{row.priority?'ACTIVE':'—'}</span></div>{row.active?.pattern?<><small>{row.active.interval} • {patternLabel(row.active.pattern)}</small><small className="coin-direction">{row.active.pattern.direction} • {(row.active.pattern.lifecycle??row.active.pattern.status)} • {row.active.pattern.quality}/100</small></>:<small>NO ACTIVE PATTERN</small>}</button>)}</div></aside>
      <section className="center-panel"><div className="card chart-card"><div className="chart-header"><div><h1>{symbol}</h1><small>{title} / Tether • BINANCE</small></div><div className="timeframes">{TFS.map(tf=><button key={tf} className={tf===interval?'active':''} onClick={()=>setInterval(tf)}>{tf}</button>)}</div></div><div className="toolbar"><button>FIT</button><button>RESET</button><label><input type="checkbox" defaultChecked/> EMA20</label><label><input type="checkbox" defaultChecked/> EMA50</label><label><input type="checkbox" checked={showAutoTrend} onChange={e=>setShowAutoTrend(e.target.checked)}/> AUTO TREND</label><label><input type="checkbox" defaultChecked/> ENTRY/SL/TP</label><label><input type="checkbox" checked={showVolume} onChange={e=>setShowVolume(e.target.checked)}/> VOLUME</label><label><input type="checkbox" defaultChecked/> PATTERNS</label></div><div className="chart-stage"><div className="trend-badge">TREND: {analysis?.structure ?? (loading?'LOADING':'UNKNOWN')}</div><div className={backendOk?'backend-badge ok':'backend-badge bad'}>{backendOk?'BACKEND LIVE':'DIRECT BINANCE FALLBACK'}</div><PatternOverlay pattern={analysis?.pattern??null}/>{analysisError&&candles.length>0&&<div className="analysis-warn">Analysis: {analysisError}</div>}{error&&!candles.length&&<div className="error-badge">{error}</div>}{loading&&<div className="loading">Loading market data…</div>}<TradingChart candles={candles} pattern={analysis?.pattern??null} showVolume={showVolume} trendLines={analysis?.trendLines??null} showAutoTrend={showAutoTrend} viewKey={`${symbol}:${interval}`}/></div><footer><span>• BINANCE SPOT • MARKET DATA</span><span>{last?`O ${last.open.toFixed(2)} H ${last.high.toFixed(2)} L ${last.low.toFixed(2)} C ${last.close.toFixed(2)}`:'—'}</span></footer></div><div className="card mtf-flow"><div className="flow-title">MTF FLOW</div><div className="flow-grid">{STAGES.map((tf,i)=><div className="flow-stage" key={tf}><b>{tf.toUpperCase()}</b><span>{i===0?'TREN UTAMA':i===1?'SETUP':i===2?'TIMING':'ENTRY CONTEXT'}</span>{i<3&&<em>↓</em>}</div>)}</div></div><div className="card order-book"><h2>Order Book</h2><div className="empty-note">Order-book module will be connected to the realtime backend stream in the next phase.</div></div></section>
      <aside className="right-panel card"><div className="right-title">Pattern Details <span>LIVE ENGINE</span></div>{analysis?.pattern?<><div className="detail-card"><h3>{analysis.pattern.name.replaceAll('_',' ')}</h3><p className="direction">{analysis.pattern.structureDirection??analysis.pattern.direction}{analysis.pattern.breakoutDirection?` • BREAKOUT ${analysis.pattern.breakoutDirection}`:''}</p><p>Status <b>{analysis.pattern.lifecycle??analysis.pattern.status}</b></p><p>Quality <b>{analysis.pattern.quality}/100</b></p>{analysis.pattern.targetPrice!=null&&<p>Target <b>{analysis.pattern.targetPrice.toFixed(4)}</b></p>}{analysis.pattern.invalidationPrice!=null&&<p>Invalidation <b>{analysis.pattern.invalidationPrice.toFixed(4)}</b></p>}<p>Breakout <b>{analysis.pattern.breakoutPrice!=null?analysis.pattern.breakoutPrice.toFixed(4):'—'}</b></p><p className="explanation">{analysis.pattern.explanation}</p></div><div className="detail-card"><h3>Validation Audit</h3>{analysis.pattern.checks.map(ch=><div className="check" key={ch.label}><span>{ch.ok?'✓':'×'}</span><div><b>{ch.label}</b><small>{ch.detail}</small></div></div>)}</div></>:<div className="detail-card"><h3>NO VALID PATTERN</h3><p className="explanation">Tidak ada struktur yang memenuhi aturan pattern pada timeframe ini.</p></div>}<div className="detail-card"><h3>Technical Summary</h3><p>Structure <b>{analysis?.structure??'—'}</b></p><p>ATR <b>{analysis?.atr?.toFixed(4)??'—'}</b></p><p>EMA20 <b>{analysis?.ema20?.toFixed(4)??'—'}</b></p><p>EMA50 <b>{analysis?.ema50?.toFixed(4)??'—'}</b></p></div></aside>
    </main>}
  </div>
}

function PatternFinderPage(props:{finderPattern:string;setFinderPattern:(v:string)=>void;finderTF:string;setFinderTF:(v:string)=>void;finderSensitivity:string;setFinderSensitivity:(v:string)=>void;finderUniverse:number;setFinderUniverse:(v:number)=>void;finderLoading:boolean;finderResults:PatternFinderMatch[];finderMeta:{scanned:number;patternLabel:string;updatedAt:number}|null;finderError:string|null;runFinder:()=>void;openMatch:(m:PatternFinderMatch)=>void}){
  const {finderPattern,setFinderPattern,finderTF,setFinderTF,finderSensitivity,setFinderSensitivity,finderUniverse,setFinderUniverse,finderLoading,finderResults,finderMeta,finderError,runFinder,openMatch}=props;
  const selected=PATTERNS.find(p=>p[0]===finderPattern) ?? PATTERNS[0];
  return <main className="finder-shell"><div className="finder-stepper"><div className="step on"><b>1</b><span>Pick Pattern<small>Browse & select</small></span></div><div className="step-line"/><div className="step on"><b>2</b><span>Configure<small>Set options</small></span></div><div className="step-line"/><div className={`step ${finderMeta?'on':''}`}><b>3</b><span>Results<small>View matches</small></span></div></div><div className="finder-heading"><span>PATTERN FINDER</span><h1>Which pattern are you hunting for?</h1><p>Scan Binance spot USDT markets for the selected chart structure, timeframe, and sensitivity.</p></div><div className="pattern-filter"><button className="active">All Patterns <small>{PATTERNS.length}</small></button></div><div className="pattern-grid">{PATTERNS.map(p=><button key={p[0]} className={`finder-pattern-card ${finderPattern===p[0]?'selected':''}`} onClick={()=>setFinderPattern(p[0])}><div className={`mini-shape ${tone(p[2])}`}><span/></div><div className="pattern-card-row"><strong>{p[1]}</strong><em className={tone(p[2])}>{p[2]}</em></div><small>{p[2]==='NEUTRAL'?'Structure-neutral':'Directional'} • live engine</small></button>)}</div><section className="finder-config card"><div className="selected-pattern"><div className={`large-mini ${tone(selected[2])}`}></div><div><strong>{selected[1]}</strong><span>{selected[2]} • Binance Pattern Engine</span></div></div><div className="config-grid"><div><h3>TIMEFRAME</h3><div className="choice-grid">{['5m','15m','30m','1h','4h','1d'].map(tf=><button key={tf} className={finderTF===tf?'active':''} onClick={()=>setFinderTF(tf)}>{tf}<small>{tf==='5m'?'Scalp':tf==='15m'?'Intraday':tf==='1h'?'Swing':tf==='4h'?'Position':tf==='1d'?'Daily':'Half-hour'}</small></button>)}</div></div><div><h3>MATCH SENSITIVITY</h3>{[['broad','Broad','More matches, lower threshold'],['balanced','Balanced','Recommended — quality/coverage'],['strict','Strict','Fewer matches, stricter threshold']].map(([v,t,d])=><button key={v} className={`sensitivity ${finderSensitivity===v?'active':''}`} onClick={()=>setFinderSensitivity(v)}><b>{t}</b><small>{d}</small></button>)}</div><div><h3>BINANCE UNIVERSE</h3><div className="choice-grid">{[100,250,500].map(n=><button key={n} className={finderUniverse===n?'active':''} onClick={()=>setFinderUniverse(n)}>{n}<small>{n===500?'Full scan':n===250?'Balanced':'Fast'}</small></button>)}</div></div></div><button className="start-scan" disabled={finderLoading} onClick={runFinder}>{finderLoading?'Scanning Binance…':'⚡ Start Scan'}</button><div className="scan-note">Scans up to {finderUniverse} USDT spot pairs • {selected[1]} • {finderTF} • {finderSensitivity}</div></section>{finderError&&<div className="finder-error">{finderError}</div>}{finderLoading&&<div className="scan-state"><div className="scan-dots">•••</div><h2>Scanning Binance markets…</h2><p>Matches akan muncul setelah engine selesai memvalidasi struktur.</p></div>}{!finderLoading&&finderMeta&&<section className="finder-results"><div className="results-head"><div><span>STEP 3 OF 3 — RESULTS</span><h2>{finderResults.length} matches found</h2><small>{finderMeta.scanned} Binance pairs scanned • {finderMeta.patternLabel}</small></div><button onClick={runFinder}>⚡ Scan Again</button></div>{finderResults.length===0?<div className="no-results">Tidak ada match yang lolos threshold pada kombinasi ini.</div>:<div className="results-list">{finderResults.map((m,i)=><button className="result-row" key={`${m.symbol}-${m.interval}`} onClick={()=>openMatch(m)}><div className="rank">{i+1}</div><div className="result-main"><div className="result-title"><strong>{m.symbol}</strong><span className={`quality q${Math.round(m.match/10)*10}`}>{m.match}%</span></div><div className="result-tags"><em className={tone(m.pattern.direction)}>{m.pattern.direction}</em><span>{m.pattern.lifecycle??m.pattern.status}</span><span>{m.signals} checks</span><span>{m.interval}</span></div><p>{m.pattern.explanation}</p></div><div className="result-action">View Chart ↗</div></button>)}</div>}</section>}</main>
}

function LiveScannerPage({radarItems,loading,onOpen}:{radarItems:RadarItem[];loading:boolean;onOpen:(item:RadarItem)=>void}){
  const items=radarItems.filter(x=>x.pattern).sort((a,b)=>((b.pattern?.quality??0)-(a.pattern?.quality??0))).slice(0,50);
  return <main className="scanner-shell"><div className="finder-heading"><span>LIVE SCANNER</span><h1>Active pattern radar</h1><p>Real-time pattern states from the current Binance watch universe.</p></div><div className="scanner-toolbar"><div className="scan-live"><i/> {loading?'Refreshing…':'LIVE'}</div><span>{items.length} active results</span></div><div className="scanner-grid">{items.map((i,idx)=><button className="scanner-card" key={`${i.symbol}-${i.interval}`} onClick={()=>onOpen(i)}><div className="rank">{idx+1}</div><div><strong>{i.symbol}</strong><small>{i.interval} • {i.pattern!.name.replaceAll('_',' ')}</small><span className={tone(i.pattern!.direction)}>{i.pattern!.direction} • {i.pattern!.lifecycle??i.pattern!.status}</span></div><b>{i.pattern!.quality}/100</b></button>)}</div></main>
}

