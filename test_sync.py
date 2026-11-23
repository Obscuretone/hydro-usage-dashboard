import asyncio
import hashlib
import json
from datetime import date
from types import SimpleNamespace

import pytest
from hydroqc.consts import LoginStatus
from hydroqc.hydro_api.consts import AUTH_CLIENTS
import sync as adapter

EMAIL='fixture@example.invalid'
CLIENT=AUTH_CLIENTS['mobile'].client_id

class MemoryCache:
    def __init__(self):
        self.meta={'synced_at':'previous-success','hydro_daily':[{'dateJourConso':'2026-09-30','tempMoyenneQuot':9}]}
        self.frames=[]
    def metadata(self,contract,payload=None):
        if payload is not None:self.meta=payload.copy()
        return self.meta.copy()
    def upsert(self,contract,frame):self.frames.append(frame.copy());return len(frame)

@pytest.fixture
def environment(monkeypatch,tmp_path):
    import hydroqc.webuser
    cache=MemoryCache();calls=[];created=[]
    class Contract:
        contract_id='fixture-contract';rate='D';rate_option=''
        cp_projected_bill=10;cp_total_consumption=20;cp_duration=30;cp_current_day=2
        async def get_periods_info(self):return []
        async def get_daily_consumption(self,start,end):
            return {'success':True,'results':[{'courant':{'dateJourConso':'2026-10-01','tempMoyenneQuot':0}}]}
        async def get_hourly_consumption(self,day):
            return {'success':True,'results':{'listeDonneesConsoEnergieHoraire':[{'heure':'00:00','consoTotal':2,'codeConso':'R'}]}}
    class User:
        session_expired=False
        def __init__(self,username,password,**kwargs):
            assert kwargs['verify_ssl'] is True
            assert kwargs['auth_client']=='mobile'
            self.token='initial';self._hydro_client=SimpleNamespace(login=self.login)
            self.customers=[SimpleNamespace(accounts=[SimpleNamespace(contracts=[Contract()])])]
            created.append(self)
        async def login(self):calls.append('login');return LoginStatus.MFA_REQUIRED
        async def submit_mfa_code(self,code):assert code=='fixture-code';return LoginStatus.SUCCESS
        async def request_mfa_code(self):calls.append('send-code')
        def export_session_state(self):return {'client_id':CLIENT,'refresh_token':self.token}
        def import_session_state(self,state):self.token=state['refresh_token']
        async def check_hq_portal_status(self):calls.append('probe');return True
        async def get_info(self):self.token='rotated'
        async def fetch_customers_info(self):pass
        async def close_session(self):calls.append('close')
    monkeypatch.setattr(hydroqc.webuser,'WebUser',User)
    monkeypatch.setattr(adapter,'Cache',lambda:cache)
    monkeypatch.setattr('builtins.input',lambda _:EMAIL)
    secrets=iter(['fixture-password','fixture-code'])
    monkeypatch.setattr(adapter.getpass,'getpass',lambda _:next(secrets))
    async def no_wait(_):pass
    monkeypatch.setattr(adapter.asyncio,'sleep',no_wait)
    args=SimpleNamespace(data_dir=str(tmp_path),use_session=False,auth_client='mobile',username_file=None,days=1,start=date(2026,10,1),end=date(2026,10,1))
    return SimpleNamespace(args=args,cache=cache,calls=calls,User=User,Contract=Contract,created=created,path=tmp_path/'session-mobile.json')

def saved(env,**changes):
    data={'owner_sha256':hashlib.sha256(EMAIL.encode()).hexdigest(),'auth_client':'mobile','contract_id':'fixture-contract','state':{'client_id':CLIENT,'refresh_token':'saved'}}
    data.update(changes);adapter.save_session(env.path,data);env.args.use_session=True

def test_interactive_mobile_mfa_retains_history_and_zero_temperature(environment):
    e=environment;asyncio.run(adapter.sync(e.args))
    assert e.calls==['login','close']
    assert e.cache.frames[0].iloc[0].temperature_c==0
    assert len(e.cache.meta['hydro_daily'])==2
    state=json.loads(e.path.read_text())
    assert state['auth_client']=='mobile' and state['state']['client_id']==CLIENT
    assert state['contract_id']=='fixture-contract'
    assert 'fixture-password' not in e.path.read_text()
    assert e.path.stat().st_mode & 0o777==0o600

def test_unattended_refresh_rotates_state_without_login(environment):
    e=environment;saved(e);asyncio.run(adapter.sync(e.args))
    assert 'login' not in e.calls and 'send-code' not in e.calls
    assert json.loads(e.path.read_text())['state']['refresh_token']=='rotated'

def test_expired_session_never_requests_email(environment):
    e=environment;saved(e);e.User.session_expired=True
    async def silent(self):return LoginStatus.FAILED
    e.User.try_silent_login=silent
    with pytest.raises(adapter.AuthenticationRequired):asyncio.run(adapter.sync(e.args))
    assert e.calls==['close']

def test_library_internal_login_is_also_blocked(environment):
    e=environment;saved(e)
    async def probe(self):return await self._hydro_client.login()
    async def silent(self):return LoginStatus.FAILED
    e.User.get_info=probe;e.User.try_silent_login=silent
    with pytest.raises(adapter.AuthenticationRequired):asyncio.run(adapter.sync(e.args))
    assert 'login' not in e.calls and 'send-code' not in e.calls

def test_rotated_token_survives_data_error(environment):
    e=environment;saved(e)
    async def failure(self):self.token='rotated-before-error';raise RuntimeError('fixture error')
    e.User.fetch_customers_info=failure
    with pytest.raises(RuntimeError):asyncio.run(adapter.sync(e.args))
    assert json.loads(e.path.read_text())['state']['refresh_token']=='rotated-before-error'
    assert e.calls[-1]=='close'

def test_partial_import_does_not_advance_last_success(environment):
    e=environment;saved(e)
    async def failure(self,day):raise ValueError('fixture response')
    e.Contract.get_hourly_consumption=failure
    with pytest.raises(adapter.ImportIncomplete):asyncio.run(adapter.sync(e.args))
    assert e.cache.meta['synced_at']=='previous-success'
    assert json.loads(e.path.read_text())['state']['refresh_token']=='rotated'

@pytest.mark.parametrize('field,value',[('auth_client','web'),('state',{'client_id':AUTH_CLIENTS['web'].client_id,'refresh_token':'wrong-client'})])
def test_cross_client_state_is_rejected_before_network(environment,field,value):
    e=environment;saved(e,**{field:value})
    with pytest.raises(adapter.AuthenticationRequired):asyncio.run(adapter.sync(e.args))
    assert not e.created

def test_new_account_cannot_overwrite_existing_session(environment):
    e=environment;saved(e,owner_sha256='different-owner');e.args.use_session=False
    previous=e.path.read_bytes()
    with pytest.raises(adapter.AuthenticationRequired):asyncio.run(adapter.sync(e.args))
    assert e.path.read_bytes()==previous and not e.created

def test_missing_mobile_state_does_not_fall_back_to_old_web_file(environment):
    e=environment;e.args.use_session=True
    (e.path.parent/'session.json').write_text('{"legacy":"web"}')
    with pytest.raises(adapter.AuthenticationRequired):asyncio.run(adapter.sync(e.args))
    assert not e.created

def test_atomic_session_failure_preserves_previous_file(tmp_path):
    p=tmp_path/'session-mobile.json';adapter.save_session(p,{'token':'previous'})
    previous=p.read_bytes()
    with pytest.raises(TypeError):adapter.save_session(p,{'token':object()})
    assert p.read_bytes()==previous
    assert list(tmp_path.iterdir())==[p]
