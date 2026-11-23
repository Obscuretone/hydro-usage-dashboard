import json,sys
from pathlib import Path
import pytest
import make_demo


def test_demo_needs_no_database_and_is_explicitly_synthetic(tmp_path,monkeypatch):
    def no_database():raise AssertionError('Demo must not use the account database')
    monkeypatch.setattr('deploy.build_snapshot.connect',no_database)
    monkeypatch.setattr(sys,'argv',['make_demo.py','--out',str(tmp_path)])
    make_demo.main()
    data=json.loads((tmp_path/'data.json').read_text())
    assert data['hours'] and all(r['quality']=='synthetic' for r in data['hours'])
    assert data['daily'] and not any(r['day']=='2026-11-01' for r in data['hours'])
    assert (tmp_path/'plotly.min.js').is_file()


def test_demo_refuses_to_overwrite_account_readings(tmp_path,monkeypatch):
    p=tmp_path/'data.json';original='{"hours":[{"quality":"R"}]}'
    p.write_text(original)
    monkeypatch.setattr(sys,'argv',['make_demo.py','--out',str(tmp_path)])
    with pytest.raises(ValueError):make_demo.main()
    assert p.read_text()==original
