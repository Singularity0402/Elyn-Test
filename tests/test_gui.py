"""GUI 스모크 (Linux/Xvfb 에서 REL-004 대용). DISPLAY 나 tkinter 가 없으면 건너뛴다."""
import os

import pandas as pd
import pytest

from conftest import offline_engine
from synthetic import planted_cached

tk = pytest.importorskip('tkinter')
pytestmark = pytest.mark.skipif(not os.environ.get('DISPLAY'), reason='DISPLAY 없음 (xvfb-run 으로 실행)')


def test_gui_boot_cycle_alert_chart_seen_close(pe):
    df, starts, cut = planted_cached(days=800)
    eng, store, clock = offline_engine(pe, df.iloc[:cut], df.index[cut - 1] + pd.Timedelta(minutes=1, seconds=20))
    out = {}

    def on_ready(app):
        app.auto_var.set(0)
        app.start_cycle(['15m'])

        def wait_cycle():
            if app.busy:
                app.root.after(200, wait_cycle)
                return
            out['trade'] = bool(app.last_final and app.last_final.get('trade'))
            app.root.after(1500, after_alert)

        def after_alert():
            out['alert_windows'] = len(app.alerts.windows)
            out['screen'] = app.txt.get('1.0', 'end')
            app.chart()
            app.root.after(3000, finish)

        def finish():
            out['chart'] = any(w.winfo_class() == 'Toplevel' and 'VISUAL AUDIT' in w.title()
                               for w in app.root.winfo_children())
            app.mark_seen()
            app.root.after(1000, app.close)
        app.root.after(300, wait_cycle)

    pe.run_gui(engine=eng, on_ready=on_ready, autoclose_ms=120000)
    assert out['trade'] and out['alert_windows'] == 1 and out['chart']
    assert 'SIDE              LONG' in out['screen'] and 'MAX LOSS' in out['screen']
    assert eng.state.read()['signals'][-1]['status'] == 'SEEN'
