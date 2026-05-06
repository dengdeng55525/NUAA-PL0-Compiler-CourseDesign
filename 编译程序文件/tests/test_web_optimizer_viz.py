import importlib


def test_web_optimizer_viz_payload_has_opt_viz_when_enabled():
    appmod = importlib.import_module('web.app')
    app = appmod.app
    client = app.test_client()

    src = """program p;
var x,y;
procedure mul(a,b);
var r;
begin
  r := a*b;
  write(r)
end;
begin
  read(x,y);
  call mul(x,y);
  write(x)
end
"""

    resp = client.post('/api/compile', json={
        'source': src,
        'inputs': [5, 3],
        'auto_recover': False,
        'enable_opt': True,
        'diag_v2': True,
        'compile_mode': 'classic',
        'view_mode': 'flat',
        'include_stats': False,
        'show_opt_viz': True,
    })
    assert resp.status_code == 200
    js = resp.get_json()
    assert js is not None
    assert 'opt_viz' in js
    assert js['opt_viz'] is not None
    assert 'before' in js['opt_viz']
    assert 'after' in js['opt_viz']
    assert isinstance(js['opt_viz']['before'], list)
    assert isinstance(js['opt_viz']['after'], list)


def test_web_optimizer_viz_payload_omits_opt_viz_when_disabled():
    appmod = importlib.import_module('web.app')
    app = appmod.app
    client = app.test_client()

    src = """program p; var x; begin x := 1; write(x) end"""

    resp = client.post('/api/compile', json={
        'source': src,
        'inputs': [],
        'auto_recover': False,
        'enable_opt': True,
        'diag_v2': True,
        'compile_mode': 'classic',
        'view_mode': 'flat',
        'include_stats': False,
        'show_opt_viz': False,
    })
    assert resp.status_code == 200
    js = resp.get_json()
    assert js is not None
    assert 'opt_viz' not in js or js['opt_viz'] in (None, {})

