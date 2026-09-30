"""
Matched-null 보정(calibration) 실험 — 엣지가 '없는' 합성 데이터에서 p-value 가 균등분포인지 본다.
보정된 검정이라면 P(p <= a) ≈ a 여야 한다.

  python experiments/null_calibration.py v611 400            # V611 analyze_scale_v500(do_null=True)
  python experiments/null_calibration.py v612 400            # V612 find_neighbors + matched_null(paired/pool)
  python experiments/null_calibration.py v612 200 --long     # K=192, 약 5.7년 15m 이력

합성 데이터: 변동성 군집이 있는 마팅게일(미래 방향이 과거와 독립). 실데이터 결과가 아니다.
"""
import importlib.util
import multiprocessing as mp
import os
import sys
import tempfile
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
from synthetic import random_walk_tf  # noqa: E402

LONG = '--long' in sys.argv
K, H, N = (192, 16, 200000) if LONG else (96, 16, 30000)


def load(which):
    if which == 'v611':
        home = tempfile.mkdtemp(prefix='pe611_')
        os.environ['HOME'] = os.environ['USERPROFILE'] = home
        cwd = os.getcwd()
        os.chdir(home)
        path = os.path.join(ROOT, '01_BASELINE', 'pattern_edge_v611_visual_audit.py')
    else:
        path = os.path.join(ROOT, 'pattern_edge_v612.py')
    spec = importlib.util.spec_from_file_location(which, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if which == 'v611':
        os.chdir(cwd)
    return m


def one_v611(seed):
    m = load('v611')
    df = random_walk_tf(N, seed)
    ch = m.Channels(df)
    r = m.analyze_scale_v500(ch, None, df.index, '15m', K, H, {}, topk=36, levels=None, use_1m=False,
                             do_null=True, rng=np.random.default_rng(seed + 7))
    return None if 'winner' not in r else dict(v611=r['pval_raw'], neff=r['nb']['n_eff'])


def one_v612(seed):
    m = load('v612')
    df = random_walk_tf(N, seed)
    ch = m.Channels(df)
    nb, err = m.find_neighbors(ch, K, H, topk=36)
    if nb is None:
        return None
    st, w = np.asarray(nb['starts']), np.asarray(nb['weights'])
    HI, LO, CL, _ = m.PathMaker(ch, None, '15m', K, H, use_1m=False).paths(st, nb['vol_scale'])
    T = m.observed_statistic(HI, LO, CL, st, w, '15m', K, H)
    if T is None:
        return None
    out = dict(neff=nb['n_eff'])
    for mode in ('paired', 'pool'):
        out[mode] = m.matched_null(ch, None, '15m', K, H, nb, T, False, n_boot=150,
                                   rng=np.random.default_rng(seed + 1), mode=mode)[0]
    return out


if __name__ == '__main__':
    which, R = sys.argv[1], int(sys.argv[2])
    t0 = time.time()
    with mp.Pool(4) as pool:
        rows = [x for x in pool.map(one_v611 if which == 'v611' else one_v612, range(1000, 1000 + R)) if x]
    print(f'{which} K={K} H={H} N={N} replicates={len(rows)} time={time.time() - t0:.0f}s '
          f'mean N_eff={np.mean([r["neff"] for r in rows]):.1f}')
    for mode in (['v611'] if which == 'v611' else ['paired', 'pool']):
        p = np.array([r[mode] for r in rows])
        print(f'  {mode:>6}: ' + '  '.join(f'P(p<={a})={np.mean(p <= a):.3f}' for a in (0.0167, 0.033, 0.05, 0.10)))
