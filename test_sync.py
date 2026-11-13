"""Mocked adapter checks: these are not live Hydro authentication tests."""
import asyncio
import json
from datetime import date
from types import SimpleNamespace
from core import Cache
import sync as adapter


def test_interactive_mfa_import_and_private_session(tmp_path,monkeypatch):
    import hydroqc.webuser
    from hydroqc.consts import LoginStatus
    calls=[]
    class Contract:
        contract_id='fixture-only'; rate='D'; rate_option=''
        cp_projected_bill=123; cp_total_consumption=45; cp_duration=60; cp_current_day=10
        async def get_periods_info(self): pass
        async def get_daily_consumption(self,start,end):
            return {'success':True,'results':[{'courant':{'dateJourConso':'2026-10-01','tempMoyenneQuot':5}}]}
        async def get_hourly_consumption(self,day):
            return {'success':True,'results':{'listeDonneesConsoEnergieHoraire':[{'heure':'00:00','consoTotal':2,'codeConso':'fixture'}]}}
    class User:
        def __init__(self,*args,**kwargs):
            assert kwargs['verify_ssl'] is True
            self.customers=[SimpleNamespace(accounts=[SimpleNamespace(contracts=[Contract()])])]
        async def login(self): calls.append('login'); return LoginStatus.MFA_REQUIRED
        async def request_mfa_code(self): calls.append('request'); return True
        async def submit_mfa_code(self,code): assert code=='fixture-code'; return LoginStatus.SUCCESS
        def export_session_state(self): return {'fake_token':'fixture'}
        async def get_info(self): pass
        async def fetch_customers_info(self): pass
        async def close_session(self): calls.append('close')
    monkeypatch.setattr(hydroqc.webuser,'WebUser',User)
    answers=iter(['fixture@example.invalid','y'])
    monkeypatch.setattr('builtins.input',lambda _:next(answers))
    secrets=iter(['fixture-password','fixture-code'])
    monkeypatch.setattr(adapter.getpass,'getpass',lambda _:next(secrets))
    async def no_wait(_): pass
    monkeypatch.setattr(adapter.asyncio,'sleep',no_wait)
    Cache(tmp_path/'hydro.sqlite').metadata('fixture-only',{'hydro_daily':[{'dateJourConso':'2026-09-30','consoTotalQuot':40,'tempMoyenneQuot':9,'codeConsoQuot':'R'}]})
    args=SimpleNamespace(data_dir=str(tmp_path),start=date(2026,10,1),end=date(2026,10,1),days=1)
    asyncio.run(adapter.sync(args))
    f=Cache(tmp_path/'hydro.sqlite').load('fixture-only')
    assert len(f)==1 and f.iloc[0].kwh==2 and f.iloc[0].temperature_c==5
    assert calls==['login','request','close']
    kept=Cache(tmp_path/'hydro.sqlite').metadata('fixture-only')['hydro_daily']
    assert [r['dateJourConso'] for r in kept]==['2026-09-30','2026-10-01']
    assert (tmp_path/'session.json').stat().st_mode & 0o777==0o600
    assert 'fixture-password' not in (tmp_path/'session.json').read_text()


def test_saved_token_refresh_does_not_require_sso_cookie():
    from hydroqc.consts import LoginStatus
    calls=[]
    class User:
        session_expired=False
        async def check_hq_portal_status(self): calls.append('init'); return True
        async def get_info(self): calls.append('token-probe')
        async def try_silent_login(self): raise AssertionError('Valid refresh token should work without cookie SSO')
    assert asyncio.run(adapter.restore_session(User()))==LoginStatus.SUCCESS
    assert calls==['init','token-probe']


def test_expired_token_falls_back_to_noninteractive_sso():
    from hydroqc.consts import LoginStatus
    class User:
        session_expired=True
        async def check_hq_portal_status(self): raise AssertionError('Do not probe expired token: wrapper may initiate interactive login')
        async def try_silent_login(self): return LoginStatus.FAILED
    assert asyncio.run(adapter.restore_session(User()))==LoginStatus.FAILED
