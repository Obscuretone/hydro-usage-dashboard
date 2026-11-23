import json
from pathlib import Path
import pytest
from deploy import build_snapshot as snapshot

class Cursor:
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def execute(self,query,args=None):self.query=query
    def __iter__(self):
        if 'DISTINCT contract' in self.query:return iter([('private-contract',)])
        return iter([('2026-11-01T04:00:00+00:00',1,0,'R'),('2026-11-02T04:00:00+00:00',2,0,'R')])
    def fetchone(self):return (json.dumps({'rate':'D','password':'NEVER-EXPORT','access_token':'NEVER-EXPORT','synced_at':'2026-11-02T06:00:00Z'}),)
class Connection:
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def cursor(self):return Cursor()

def test_refresh_export_whitelists_status_and_keeps_dst_coverage(tmp_path,monkeypatch):
    monkeypatch.setattr(snapshot,'connect',lambda:Connection())
    assets=tmp_path/'assets';assets.mkdir()
    for name in ['index.html','app.js','style.css','plotly.min.js']:(assets/name).write_text('fixture')
    snapshot.build(tmp_path/'out',assets,status={'state':'sign_in_required','last_attempt_at':'2026-11-03T00:00:00Z','last_success_at':'2026-11-02T06:00:00Z','password':'NEVER-EXPORT'})
    raw=(tmp_path/'out/data.json').read_text();data=json.loads(raw)
    assert data['refresh']['state']=='sign_in_required'
    assert data['expected']['2026-11-01']==25
    assert 'NEVER-EXPORT' not in raw and 'private-contract' not in raw
    assert set(data['refresh'])=={'state','last_attempt_at','last_success_at'}
