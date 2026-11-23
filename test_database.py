"""Opt-in integration checks against an explicitly named disposable MariaDB."""
import os
from uuid import uuid4
import pandas as pd
import pytest
from core import Cache
from deploy.hydro_store import connect

@pytest.fixture
def database(monkeypatch):
    name=os.environ.get('HYDRO_TEST_DATABASE')
    if not name:pytest.skip('Set HYDRO_TEST_DATABASE to a dedicated hydro_test_* database')
    if not name.startswith('hydro_test_'):
        pytest.fail('Refusing integration tests outside a hydro_test_* database')
    monkeypatch.setenv('HYDRO_DB_NAME',name)
    contracts=[str(uuid4()),str(uuid4())]
    with connect() as c,c.cursor() as d:
        d.execute('SELECT DATABASE()');assert d.fetchone()[0]==name
    try:yield Cache(),contracts
    finally:
        with connect() as c,c.cursor() as d:
            for contract in contracts:
                d.execute('DELETE FROM hours WHERE contract=%s',(contract,))
                d.execute('DELETE FROM metadata WHERE contract=%s',(contract,))
            c.commit()

def hours():
    ts=pd.date_range('2026-10-01','2026-10-02',freq='h',inclusive='left',tz='America/Toronto')
    return pd.DataFrame({'timestamp':ts,'kwh':1})

def test_cache_idempotence_contract_isolation_and_metadata(database):
    cache,(a,b)=database;f=hours()
    cache.upsert(a,f);cache.upsert(a,f);cache.upsert(b,f.assign(kwh=2))
    assert len(cache.load(a))==24 and cache.load(b).kwh.sum()==48
    cache.upsert(a,f.iloc[:1].assign(kwh=4))
    assert cache.load(a).kwh.sum()==27
    cache.metadata(a,{'fixture':'one'});cache.metadata(b,{'fixture':'two'})
    assert cache.metadata(a)=={'fixture':'one'} and cache.metadata(b)=={'fixture':'two'}

def test_invalid_import_writes_no_partial_rows(database):
    cache,(a,_)=database;f=hours();f.loc[23,'kwh']=-1
    with pytest.raises(ValueError):cache.upsert(a,f)
    assert cache.load(a).empty
