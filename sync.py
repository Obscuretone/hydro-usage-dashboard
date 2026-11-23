"""Interactive local HydroQC importer. Passwords are never written to disk."""
import argparse
import asyncio
import getpass
import hashlib
import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
import pandas as pd
from core import Cache, TZ, parse_hourly


class AuthenticationRequired(Exception):
    """A person must complete Hydro authentication; do not retry email login."""


class ImportIncomplete(Exception):
    """The requested import did not complete; retain the last successful time."""


def save_session(path, state):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    # Replace atomically: a crash or serialization failure must not destroy a
    # usable refresh token. mkstemp creates the sibling file owner-only.
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(state,f,allow_nan=False)
            f.flush();os.fsync(f.fileno())
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


async def restore_session(user):
    """Refresh a saved OAuth token before trying the browser SSO cookie.

    The portal status call initializes the wrapper's HTTP session. A cookie-only
    silent login can fail even while the refresh token remains valid.
    """
    from hydroqc.consts import LoginStatus
    from hydroqc.error import HydroQcMFARequiredError
    if not user.session_expired:
        try:
            await user.check_hq_portal_status()
            await user.get_info()
            return LoginStatus.SUCCESS
        except Exception:
            pass
    try:
        return await user.try_silent_login()
    except HydroQcMFARequiredError:
        raise AuthenticationRequired('Saved session needs interactive sign-in.') from None


async def sync(args):
    from hydroqc.webuser import WebUser
    from hydroqc.consts import LoginStatus
    import logging
    logging.disable(logging.CRITICAL)  # upstream logger names can contain account identifiers
    folder=Path(args.data_dir); folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    client=getattr(args,'auth_client','mobile')
    session=folder/f'session-{client}.json'
    saved=json.loads(session.read_text()) if session.exists() else {}
    unattended=getattr(args,'use_session',False)
    username_file=getattr(args,'username_file',None)
    username='' if unattended else (Path(username_file).read_text().strip() if username_file else input('Hydro login email: ').strip())
    owner=hashlib.sha256(username.casefold().encode()).hexdigest()
    password='' if unattended else getpass.getpass('Password (not saved): ')
    if unattended:
        if not saved.get('owner_sha256'):
            raise AuthenticationRequired('No saved session. Run interactively first.')
        owner=saved['owner_sha256']
    elif saved and saved.get('owner_sha256')!=owner:
        raise AuthenticationRequired('Use a separate data directory for a different account.')
    from hydroqc.hydro_api.consts import AUTH_CLIENTS
    expected_id=AUTH_CLIENTS[client].client_id
    if saved and saved.get('owner_sha256')==owner:
        if saved.get('auth_client')!=client or saved.get('state',{}).get('client_id')!=expected_id:
            raise AuthenticationRequired('Stored session belongs to a different authentication client.')
    user=WebUser(username,password,verify_ssl=True,log_level='CRITICAL',http_log_level='CRITICAL',auth_client=client)
    if unattended:
        async def no_background_login(*_args,**_kwargs):
            raise AuthenticationRequired('Interactive sign-in is required; background email login is disabled.')
        # The wrapper may initiate login from a data call if a token expires.
        # Stop that path as well as our own explicit login path.
        user.login=no_background_login
        if hasattr(user,'_hydro_client'):
            user._hydro_client.login=no_background_login
    authenticated=False
    selected_contract=saved.get('contract_id') if saved.get('owner_sha256')==owner else None
    def persist():
        state=user.export_session_state()
        if state.get('client_id')!=expected_id:
            raise AuthenticationRequired('Refusing a session for a different authentication client.')
        save_session(session,{'owner_sha256':owner,'auth_client':client,'contract_id':selected_contract,'state':state})
    try:
        status=LoginStatus.FAILED
        if session.exists():
            saved=json.loads(session.read_text())
            if saved.get('owner_sha256')==owner:
                user.import_session_state(saved['state'])
                try:
                    status=await restore_session(user)
                finally:
                    # A successful token refresh may precede a failed data call.
                    # Persist the rotated state before trying further operations.
                    persist()
        if status != LoginStatus.SUCCESS:
            if unattended:
                raise AuthenticationRequired('Saved session needs interactive sign-in.')
            status=await user.login()
        if status == LoginStatus.MFA_REQUIRED:
            # login may already have sent the code; explicitly request only on user choice.
            code=getpass.getpass('Email code (empty to request a new code): ')
            if not code.strip():
                await user.request_mfa_code()
                code=getpass.getpass('Email code: ')
            status=await user.submit_mfa_code(code.strip())
        if status != LoginStatus.SUCCESS:
            raise AuthenticationRequired('Authentication did not complete. Retry in the Hydro portal first.')
        authenticated=True
        persist()
        await user.get_info(); await user.fetch_customers_info()
        contracts=[c for cu in user.customers for a in cu.accounts for c in a.contracts]
        if not contracts:
            raise ValueError('No accessible contracts returned.')
        if selected_contract:
            selected=next((i for i,c in enumerate(contracts) if c.contract_id==selected_contract),-1)
            if selected<0:raise AuthenticationRequired('Previously selected contract is no longer available.')
        elif unattended and len(contracts)>1:
            raise AuthenticationRequired('Select a contract interactively before unattended use.')
        else:
            if len(contracts)>1:
                for i,c in enumerate(contracts):print(f'{i}: contract ending {c.contract_id[-4:]} — rate {c.rate} {c.rate_option}')
            selected=int(input('Choose contract index: ')) if len(contracts)>1 else 0
        if selected<0 or selected>=len(contracts):
            raise ValueError('Invalid contract index.')
        c=contracts[selected];selected_contract=c.contract_id;persist();cache=Cache()
        periods=await c.get_periods_info()
        period_fields=['dateDebutPeriode','dateFinPeriode','dateDerniereLecturePeriode','nbJourLecturePeriode','nbJourPrevuPeriode','consoTotalPeriode','moyenneKwhJourPeriode','montantFacturePeriode','montantProjetePeriode','tempMoyennePeriode','montantChauffagePeriode','montantVenteTranche1','montantVenteTranche2','montantVenteFraisAccesReseau','montantCreditCPC']
        safe_periods=[{k:p.get(k) for k in period_fields} for p in (periods or [])]
        meta={'rate':c.rate,'option':c.rate_option,
              'hydro_projected_bill':c.cp_projected_bill,'hydro_period_kwh':c.cp_total_consumption,
              'hydro_period_days':c.cp_duration,'hydro_read_days':c.cp_current_day,'billing_periods':safe_periods}
        previous_meta=cache.metadata(c.contract_id)
        meta['synced_at']=previous_meta.get('synced_at')
        end=args.end or datetime.now().astimezone(__import__('zoneinfo').ZoneInfo(TZ)).date()-timedelta(days=1)
        start=args.start or end-timedelta(days=args.days-1)
        if start>end or (end-start).days>731:
            raise ValueError('Choose an inclusive range of at most 732 days.')
        temps={}
        daily_readings=[]
        # Daily endpoint supplies the local station temperature; not assumed Montréal.
        try:
            response=await c.get_daily_consumption(start,end)
            if response.get('success'):
                for item in response['results']:
                    row=item['courant']; temps[str(row['dateJourConso'])[:10]]=row.get('tempMoyenneQuot')
                    daily_readings.append({k:row.get(k) for k in ['dateJourConso','consoTotalQuot','tempMoyenneQuot','codeConsoQuot']})
        except Exception:
            print('Daily temperatures unavailable; hourly import will continue without them.')
        daily_by_date={r['dateJourConso']:r for r in previous_meta.get('hydro_daily',[])}
        daily_by_date.update({r['dateJourConso']:r for r in daily_readings})
        meta['hydro_daily']=[daily_by_date[k] for k in sorted(daily_by_date)]
        cache.metadata(c.contract_id,meta)
        cursor=start; total=0; failures=0
        while cursor<=end:
            try:
                f=parse_hourly(await c.get_hourly_consumption(cursor),cursor)
                if not f.empty:
                    f['temperature_c']=temps.get(cursor.isoformat())
                    total+=cache.upsert(c.contract_id,f)
                print(f'{cursor}: {len(f)} hourly readings')
            except AuthenticationRequired:
                raise
            except Exception as exc:
                failures+=1
                # Avoid response bodies/identifiers or tokens in logs.
                print(f'{cursor}: not imported ({type(exc).__name__}); gap retained.')
                if failures>=5:
                    print('Stopped after five failed days. Retry a smaller range or use CSV.'); break
            cursor+=timedelta(days=1)
            await asyncio.sleep(1)
        if failures or total==0:
            raise ImportIncomplete('Requested dates did not all import successfully.')
        meta['synced_at']=datetime.now().astimezone().isoformat()
        cache.metadata(c.contract_id,meta)
        print(f'Saved {total} readings locally. Failed days: {failures}. Re-running upserts readings safely.')
    finally:
        try:
            if authenticated:persist()
        finally:
            await user.close_session()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',default='data')
    p.add_argument('--auth-client',choices=['web','mobile'],default='mobile')
    p.add_argument('--username-file',help='Optional owner-only local file containing the login email; password is still prompted and never saved.')
    p.add_argument('--use-session',action='store_true',help='Use the saved local session without requesting a password; fails if interactive login is needed.')
    p.add_argument('--days',type=int,default=7,choices=range(1,733),metavar='1..732')
    p.add_argument('--start',type=date.fromisoformat)
    p.add_argument('--end',type=date.fromisoformat)
    args=p.parse_args()
    try:
        asyncio.run(sync(args))
    except AuthenticationRequired as exc:
        print('Hydro sign-in required: '+str(exc))
        raise SystemExit(20)
    except (Exception,KeyboardInterrupt) as exc:
        print(f'Sync stopped ({type(exc).__name__}). No sensitive response details printed. See README integration notes.')
        raise SystemExit(1)
