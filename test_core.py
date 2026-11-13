from datetime import date
import pandas as pd
import numpy as np
import pytest
from core import Cache, normalize, daily, heating_fit, rate_d, unusual, demo, parse_hourly


def hours(start,end,value=1):
    t=pd.date_range(start,end,freq='h',inclusive='left',tz='America/Toronto')
    return pd.DataFrame({'timestamp':t,'kwh':value})


def test_cache_idempotent_and_contract_isolated(tmp_path):
    c=Cache(tmp_path/'db.sqlite'); f=hours('2026-10-01','2026-10-02')
    c.upsert('a',f); c.upsert('a',f); c.upsert('b',f.assign(kwh=2))
    assert len(c.load('a'))==24
    assert c.load('b').kwh.sum()==48
    c.upsert('a',f.iloc[:1].assign(kwh=4))
    assert c.load('a').kwh.sum()==27
    assert (c.path.stat().st_mode & 0o777)==0o600


def test_invalid_import_is_atomic(tmp_path):
    c=Cache(tmp_path/'db'); f=hours('2026-10-01','2026-10-02'); f.loc[23,'kwh']=-1
    with pytest.raises(ValueError): c.upsert('a',f)
    assert c.load('a').empty


@pytest.mark.parametrize('value',[-1,float('nan'),float('inf')])
def test_bad_energy(value):
    with pytest.raises(ValueError): normalize(pd.DataFrame({'timestamp':['2026-10-01T00:00:00-04:00'],'kwh':[value]}))


def test_ambiguous_times_rejected_but_offsets_preserve_fold():
    with pytest.raises(ValueError): normalize(pd.DataFrame({'timestamp':['2026-11-01T01:00:00'],'kwh':[1]}))
    f=normalize(pd.DataFrame({'timestamp':['2026-11-01T01:00:00-04:00','2026-11-01T01:00:00-05:00'],'kwh':[1,2]}))
    assert len(f)==2 and f.timestamp.nunique()==2
    with pytest.raises(ValueError): normalize(pd.concat([f,f]))


@pytest.mark.parametrize('start,end,count',[('2026-03-08','2026-03-09',23),('2026-11-01','2026-11-02',25)])
def test_dst_complete_days(start,end,count):
    f=hours(start,end).assign(temperature_c=0)
    d=daily(f); assert d.iloc[0].expected==count and d.iloc[0].complete
    d=daily(f.iloc[:-1]); assert not d.iloc[0].complete
    assert d.iloc[0].kwh==count-1


def test_period_tier_not_daily_threshold():
    result=rate_d(100,2,date(2026,10,1),date(2026,10,2))
    assert result['high_kwh']==20
    assert result['total']==pytest.approx(2*.46154+80*.07065+20*.11142)
    assert rate_d(0,2,date(2026,10,1),date(2026,10,2))['total']==pytest.approx(.92308)
    with pytest.raises(ValueError): rate_d(1,1,date(2026,3,31),date(2026,3,31))
    with pytest.raises(ValueError): rate_d(1,1,date(2026,10,1),date(2026,10,1),'DT')


def test_heating_regression_recovers_known_relationship_and_excludes_gaps():
    temps=np.linspace(-5,15,20)
    d=pd.DataFrame({'day':pd.date_range('2026-10-01',periods=20).date,'kwh':10+3*(18-temps),'temperature_c':temps,'complete':True})
    fit=heating_fit(d)
    assert fit['slope']==pytest.approx(3)
    assert fit['intercept']==pytest.approx(10)
    assert fit['r2']==pytest.approx(1)
    d.loc[:7,'complete']=False
    assert heating_fit(d) is None


def test_robust_unusual_hour_detection():
    f=hours('2026-10-01','2026-10-20'); f.loc[50,'kwh']=8
    flagged=unusual(f)
    assert len(flagged)==1 and flagged.iloc[0].excess_kwh==7
    assert unusual(f.iloc[:24]).empty


def test_hourly_json_preserves_null_as_gap_and_quality():
    payload={'success':True,'results':{'listeDonneesConsoEnergieHoraire':[{'heure':'00:00','consoTotal':1,'codeConso':'R'},{'heure':'01:00','consoTotal':None}]}}
    f=parse_hourly(payload,date(2026,10,1))
    assert len(f)==1 and f.iloc[0].quality=='R'
    with pytest.raises(ValueError): parse_hourly(payload,date(2026,11,1))
    payload['results']['listeDonneesConsoEnergieHoraire'][0]['heure']='24:00'
    with pytest.raises(ValueError): parse_hourly(payload,date(2026,10,1))


def test_synthetic_demo_deterministic():
    pd.testing.assert_frame_equal(demo(),demo())
    assert set(demo().quality)=={'synthetic'}


def test_live_shape_seconds_and_flagged_partial_day():
    payload={'success':True,'results':{'indErreurJourneeEnergie':True,'listeDonneesConsoEnergieHoraire':[{'heure':'00:00:00','consoTotal':1.23,'codeConso':'R'},{'heure':'01:00:00','consoTotal':None}]}}
    f=parse_hourly(payload,date(2026,11,5))
    assert len(f)==1 and f.iloc[0].kwh==1.23
    assert f.iloc[0].quality=='R;day_flagged'
    f.timestamp=pd.to_datetime(f.timestamp,utc=True).dt.tz_convert('America/Toronto')
    assert not daily(f).iloc[0].complete


def test_portal_daily_does_not_invent_missing_energy_or_temperature():
    from core import portal_daily
    f=portal_daily([
        {'dateJourConso':'2026-11-05','consoTotalQuot':30.5,'tempMoyenneQuot':16,'codeConsoQuot':'R'},
        {'dateJourConso':'2026-11-06','consoTotalQuot':None},
        {'dateJourConso':'2026-11-07','consoTotalQuot':28.5,'tempMoyenneQuot':None,'codeConsoQuot':'E'}])
    assert len(f)==2 and f.kwh.sum()==pytest.approx(59.0)
    assert pd.isna(f.iloc[1].temperature_c) and not f.iloc[1].complete
    with pytest.raises(ValueError): portal_daily([{'dateJourConso':'2026-11-05','consoTotalQuot':1}]*2)
