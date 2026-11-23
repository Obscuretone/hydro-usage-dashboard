from datetime import datetime,timezone
import json
import pytest
from deploy import weather

NOW=datetime(2026,11,23,23,45,tzinfo=timezone.utc)
def raw():
    return {'current':{'time':NOW.timestamp()-900,'temperature_2m':0},
            'hourly':{'time':[NOW.timestamp()-2700,NOW.timestamp()+900], 'temperature_2m':[0,8]}}

def test_current_zero_and_only_elapsed_hourly_estimates():
    result=weather.parse_response(raw(),None,'Example',NOW)
    assert result['current']['temp']==0
    assert len(result['hourly'])==1 and result['hourly'][0]['temp']==0
    assert 'latitude' not in result and 'longitude' not in result

@pytest.mark.parametrize('field,value',[('time',NOW.timestamp()+7200),('temperature_2m',float('nan'))])
def test_invalid_current_data_rejected(field,value):
    r=raw();r['current'][field]=value
    with pytest.raises(ValueError):weather.parse_response(r,None,'Example',NOW)

def test_weather_outage_keeps_reading_and_original_timestamp(tmp_path,monkeypatch):
    (tmp_path/'weather-config.json').write_text(json.dumps({'latitude':40,'longitude':-70}))
    previous=weather.parse_response(raw(),None,'Example',NOW)
    weather.save(tmp_path/'weather-cache.json',previous)
    def fail(*a,**kw):raise OSError('fixture outage')
    monkeypatch.setattr(weather.urllib.request,'urlopen',fail)
    result=weather.refresh_weather(tmp_path)
    assert result['state']=='fetch_failed'
    assert result['current']==previous['current']
    assert result['fetched_at']==previous['fetched_at']
    assert (tmp_path/'weather-cache.json').stat().st_mode & 0o777==0o600
