import importlib.util,json
from pathlib import Path
from types import SimpleNamespace
import pytest

spec=importlib.util.spec_from_file_location('refresh',Path(__file__).parent/'deploy/refresh.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

@pytest.mark.parametrize('code,expected',[(0,'ok'),(20,'sign_in_required'),(1,'sync_failed')])
def test_result_is_published_without_false_success(tmp_path,monkeypatch,code,expected):
    monkeypatch.setattr(module,'STATE',tmp_path)
    monkeypatch.setattr(module,'STATUS',tmp_path/'status.json')
    module.write_status({'state':'ok','last_success_at':'previous-success'})
    captured=[]
    def run(command,**kwargs):
        assert command[command.index('--auth-client')+1]=='mobile'
        assert '--use-session' in command
        assert command[command.index('--data-dir')+1]==str(tmp_path)
        assert kwargs['stdin']==module.subprocess.DEVNULL
        return SimpleNamespace(returncode=code)
    monkeypatch.setattr(module.subprocess,'run',run)
    monkeypatch.setattr(module,'publish',lambda value:captured.append(value.copy()))
    monkeypatch.setattr(module.sys,'argv',['hourly_refresh.py'])
    if code:
        with pytest.raises(SystemExit) as exc:module.main()
        assert exc.value.code==code
    else:module.main()
    assert captured[0]['state']==expected
    assert captured[0]['last_attempt_at']
    if code:assert captured[0]['last_success_at']=='previous-success'
    else:assert captured[0]['last_success_at']!='previous-success'
    assert module.STATUS.stat().st_mode & 0o777==0o600


def test_timeout_leaves_visible_failure_and_previous_success(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'STATE',tmp_path);monkeypatch.setattr(module,'STATUS',tmp_path/'status.json')
    module.write_status({'last_success_at':'previous'})
    def fail(*args,**kwargs):raise module.subprocess.TimeoutExpired('fixture',240)
    monkeypatch.setattr(module.subprocess,'run',fail)
    captured=[];monkeypatch.setattr(module,'publish',lambda value:captured.append(value.copy()))
    monkeypatch.setattr(module.sys,'argv',['hourly_refresh.py'])
    with pytest.raises(SystemExit):module.main()
    assert captured[0]['state']=='sync_failed' and captured[0]['last_success_at']=='previous'


def test_failed_build_keeps_served_snapshot(tmp_path,monkeypatch):
    public=tmp_path/'public';public.mkdir()
    old=public/'previous';old.mkdir();(old/'data.json').write_text('previous fixture')
    (public/'current').symlink_to(old,target_is_directory=True)
    monkeypatch.setattr(module,'PUBLIC',public)
    def fail(out,assets,**kwargs):
        out.mkdir();(out/'data.json').write_text('partial fixture')
        raise ValueError('fixture serialization failure')
    monkeypatch.setattr(module,'build',fail)
    with pytest.raises(ValueError):module.publish({'state':'ok'})
    assert (public/'current/data.json').read_text()=='previous fixture'
    assert {p.name for p in public.iterdir()}=={'previous','current'}


def test_weather_only_never_contacts_hydro_or_advances_success(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'STATE',tmp_path);monkeypatch.setattr(module,'STATUS',tmp_path/'status.json')
    module.write_status({'last_success_at':'previous','state':'ok'})
    monkeypatch.setattr(module.sys,'argv',['refresh.py','--weather-only'])
    def forbidden(*a,**kw):raise AssertionError('Hydro must not run for weather-only refresh')
    monkeypatch.setattr(module.subprocess,'run',forbidden)
    monkeypatch.setattr(module,'refresh_weather',lambda state:None)
    captured=[];monkeypatch.setattr(module,'publish',lambda status:captured.append(status))
    module.main()
    assert captured[0]=={'last_success_at':'previous','state':'ok'}
