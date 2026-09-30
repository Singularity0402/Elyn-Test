"""Release acceptance 중 오프라인으로 확인 가능한 항목 (REL-001/002/005/012/014)."""
import ast
import os
import py_compile
import subprocess
import sys

from conftest import V612_PATH, ROOT

STDLIB_OR_THIRD_PARTY = {
    '__future__', 'io', 'os', 'sys', 'json', 'math', 'time', 'copy', 'queue', 'random', 'zipfile', 'hashlib',
    'logging', 'threading', 'traceback', 'contextlib', 'datetime', 'urllib', 'importlib', 'zoneinfo',
    'numpy', 'pandas', 'requests', 'numba', 'tkinter', 'matplotlib', 'winsound', 'ctypes', 'tempfile',
}


def test_rel001_py_compile():
    py_compile.compile(V612_PATH, doraise=True)


def test_rel002_import_has_no_filesystem_side_effects(tmp_path):
    """import 만으로는 어떤 폴더/파일도 만들지 않는다 (V611 은 import 시 데이터 폴더 생성)."""
    home = tmp_path / 'home'
    home.mkdir()
    import site
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PATTERNEDGE_HOME=str(tmp_path / 'data'),
               PYTHONUSERBASE=site.getuserbase())          # HOME 을 바꿔도 사용자 site-packages 는 유지
    code = ('import importlib.util as u; s=u.spec_from_file_location("x", r"%s"); '
            'm=u.module_from_spec(s); s.loader.exec_module(m); print(m.__version__)') % V612_PATH
    out = subprocess.run([sys.executable, '-c', code], cwd=str(tmp_path), env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert 'V612' in out.stdout
    assert not (tmp_path / 'data').exists()
    created = sorted(p.name for p in tmp_path.iterdir())
    assert created == ['home'], created
    assert not any(p.name.startswith('C:') for p in home.iterdir())


def test_v611_import_side_effect_documented(pe611):
    """비교: V611 은 import 시 BASE_DIR 을 만든다 (비윈도우에서는 cwd 에 'C:\\CoinData_Matrix' 폴더)."""
    assert pe611.BASE_DIR == r'C:\CoinData_Matrix' or os.path.isdir(pe611.BASE_DIR)


def test_rel005_first_run_creates_directories(pe, tmp_path):
    base = pe.Paths.init(str(tmp_path / 'fresh'))
    assert os.path.isdir(os.path.join(base, 'raw'))


def test_rel012_no_private_or_signed_endpoints_in_source(pe):
    src = open(V612_PATH, encoding='utf-8').read()
    for tok in ['X-MBX-APIKEY', '/fapi/v1/order', '/fapi/v1/leverage', '/fapi/v1/marginType', 'hmac.new',
                'api_secret', '/sapi/', 'listenKey', 'signature=']:
        if tok == 'signature=':
            # 허용목록의 '차단 규칙' 문자열 한 곳만 허용
            assert src.count(tok) == 1 and "'signature=' in q" in src
        else:
            assert tok not in src, tok


def test_rel012_allowlist_blocks_everything_but_public_market_data(pe):
    import pytest
    for url in ['https://fapi.binance.com/fapi/v1/order?symbol=BTCUSDT',
                'https://fapi.binance.com/fapi/v2/account',
                'https://api.binance.com/api/v3/order',
                'http://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT',
                'https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&timestamp=1&signature=abc',
                'https://evil.example.com/fapi/v1/klines']:
        with pytest.raises(PermissionError):
            pe.PublicHttp.check_allowed(url)
    assert pe.PublicHttp.check_allowed('https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m')
    assert pe.PublicHttp.check_allowed('https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/x.zip')


def test_rel014_single_file_no_local_imports():
    tree = ast.parse(open(V612_PATH, encoding='utf-8').read())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split('.')[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split('.')[0])
    assert mods <= STDLIB_OR_THIRD_PARTY, mods - STDLIB_OR_THIRD_PARTY
    assert os.path.basename(V612_PATH) == 'pattern_edge_v612.py'


def test_version_string_matches_filename(pe):
    assert pe.VERSION == 'V612' and pe.__version__.startswith('V612') and pe.SCRIPT_NAME == 'pattern_edge_v612.py'


def test_selftest_passes(pe):
    ok, results = pe.selftest(verbose=False)
    assert ok, [r for r in results if not r[1]]


def test_baseline_is_byte_identical():
    import hashlib
    p = os.path.join(ROOT, '01_BASELINE', 'pattern_edge_v611_visual_audit.py')
    assert hashlib.sha256(open(p, 'rb').read()).hexdigest() == \
        '60782472976e78e8d5124e70d5d7b9d48a54b70b46a337b639ae40545886775e'
