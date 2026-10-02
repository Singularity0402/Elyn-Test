import importlib.util
import os
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V612_PATH = os.path.join(ROOT, 'pattern_edge_v612.py')
V611_PATH = os.path.join(ROOT, '01_BASELINE', 'pattern_edge_v611_visual_audit.py')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # 병렬 워크포워드가 작업 함수를 pickle 할 수 있도록
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='session')
def _pe_module():
    return _load(V612_PATH, 'pe612_under_test')


@pytest.fixture()
def pe(_pe_module, tmp_path, monkeypatch):
    """V612 모듈 (세션 1회 로드) + 테스트마다 격리된 데이터 폴더·시계·HEALTH."""
    m = _pe_module
    monkeypatch.setenv('PATTERNEDGE_HOME', str(tmp_path / 'home'))
    orig_utcnow = m.utcnow
    m.Paths.base = None
    m.Paths.init(str(tmp_path / 'home'))
    m.HEALTH.items.clear()
    yield m
    m.utcnow = orig_utcnow
    m.HEALTH.items.clear()
    m.Paths.base = None


@pytest.fixture(scope='session')
def pe611():
    """V611 baseline — import 부작용(C:\\CoinData_Matrix 폴더 생성)을 임시 HOME/cwd 에 가둔다."""
    home = tempfile.mkdtemp(prefix='pe611_')
    old_env = {k: os.environ.get(k) for k in ('HOME', 'USERPROFILE')}
    old_cwd = os.getcwd()
    os.environ['HOME'] = os.environ['USERPROFILE'] = home
    os.chdir(home)
    try:
        m = _load(V611_PATH, 'pe611_baseline')
    finally:
        os.chdir(old_cwd)
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return m


class Clock:
    def __init__(self, t):
        self.t = pd.Timestamp(t).to_pydatetime()

    def __call__(self):
        return self.t


def offline_engine(m, base, now):
    """네트워크 없는 엔진: 공개 API 비활성, 1분봉 주입, 시계 고정."""
    clock = Clock(now)
    m.utcnow = clock
    http = m.PublicHttp(enabled=False)
    store = m.DataStore(http)
    store.set_base(base)
    return m.Engine(store=store, http=http), store, clock
