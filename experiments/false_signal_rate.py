"""System-level false-signal rate in a NO-EDGE market (1m random walk with vol clustering).
Same series, same end points: V611 scan_model_v600 (15m) vs V612 scan_tf (15m). Fraction of scans that emit a trade."""
#   python experiments/false_signal_rate.py 60      (4 개 합성 시계열 × 60 시점, 15m 모델)
import sys, os, numpy as np, pandas as pd, multiprocessing as mp, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from null_calibration import load
m = load('v612')
SEEDS, PER = 4, int(sys.argv[1]) if len(sys.argv) > 1 else 60

def job(args):
    series_seed, ends = args
    m6 = load('v611')
    base = m._synthetic_1m(2555, seed=series_seed)
    snap = m.Snapshot(base, base.index[-1].to_pydatetime() + pd.Timedelta(minutes=1))
    tfdf = snap.tf('15m')
    out = []
    for t in ends:
        rec = dict(series=series_seed, t=int(t))
        d = m.scan_tf(snap, '15m', 10000.0, m.NEUTRAL_CONTEXT, book={}, do_null=True, end=int(t), live=False)
        rec['v612_trade'] = bool(d.get('trade')); rec['v612_reason'] = d.get('reason', '')[:60]
        rec['v612_null_run'] = bool(d.get('null_n'))
        # V611 on the same truncated history
        cut_time = tfdf.index[int(t) - 1] + pd.Timedelta(minutes=15)
        b1 = base[base.index < cut_time]
        df15 = tfdf.iloc[:int(t)][['open', 'high', 'low', 'close', 'volume', 'taker_buy_base', 'trades', 'era']]
        class DM:
            base = b1
            def get(self, tf, force_refresh=False): return df15
        try:
            p = m6.scan_model_v600(DM(), 10000.0, '15m', {}, {'closed': []}, do_null=True)
            rec['v611_trade'] = bool(p.get('trade')); rec['v611_crash'] = False; rec['v611_reason'] = p.get('reason', '')[:60]
        except Exception as e:
            rec['v611_trade'] = False; rec['v611_crash'] = True; rec['v611_reason'] = f'{type(e).__name__}: {e}'[:80]
        out.append(rec)
    return out

if __name__ == '__main__':
    g = np.random.default_rng(0)
    tasks = []
    for s in range(SEEDS):
        n15 = 2555 * 96
        ends = np.sort(g.integers(int(n15 * 0.6), n15 - 20, size=PER))
        tasks.append((100 + s, ends))
    t0 = time.time()
    with mp.Pool(4) as pool:
        rows = [r for chunk in pool.map(job, tasks) for r in chunk]
    n = len(rows)
    v612 = np.mean([r['v612_trade'] for r in rows]); v611 = np.mean([r['v611_trade'] for r in rows])
    crash = np.mean([r['v611_crash'] for r in rows]); nullrun = np.mean([r['v612_null_run'] for r in rows])
    print(f'scans={n} time={time.time()-t0:.0f}s')
    print(f'  V611 scan_model_v600: trade rate {v611:.3f}  | crash (F-01 etc) rate {crash:.3f}')
    print(f'  V612 scan_tf        : trade rate {v612:.3f}  | reached matched-null {nullrun:.3f}')
    from collections import Counter
    print('  V611 crash reasons:', Counter(r['v611_reason'][:40] for r in rows if r['v611_crash']).most_common(3))
