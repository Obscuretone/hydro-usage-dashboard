"""Optional city-level Open-Meteo estimates; independent of Hydro authentication."""
import json,math,os,tempfile,urllib.parse,urllib.request
from datetime import datetime,timezone,timedelta
from pathlib import Path


def load_weather(state):
    try:
        value=json.loads((Path(state)/'weather-cache.json').read_text())
        return value if isinstance(value,dict) else None
    except (OSError,ValueError):return None


def save(path,value):
    fd,name=tempfile.mkstemp(prefix='.weather-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,allow_nan=False);f.flush();os.fsync(f.fileno())
        Path(name).replace(path)
    finally:Path(name).unlink(missing_ok=True)


def parse_response(raw,previous,label,now):
    def temp(value):
        if value is None:return None
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not -80<=value<=60:
            raise ValueError('Invalid weather temperature')
        return value
    def instant(epoch):
        if isinstance(epoch,bool) or not isinstance(epoch,(int,float)):raise ValueError('Invalid weather timestamp')
        return datetime.fromtimestamp(epoch,timezone.utc)
    current=raw['current'];stamp=instant(current['time'])
    if stamp>now+timedelta(minutes=5):raise ValueError('Future current-weather timestamp')
    current_temp=temp(current['temperature_2m'])
    if current_temp is None:raise ValueError('Current temperature missing')
    hourly=raw['hourly'];times=hourly['time'];values=hourly['temperature_2m']
    if len(times)!=len(values):raise ValueError('Mismatched weather arrays')
    cutoff=(now-timedelta(days=370)).isoformat()
    merged={r['time']:r for r in (previous or {}).get('hourly',[]) if r['time']>=cutoff}
    count=0
    for epoch,value in zip(times,values):
        t=instant(epoch);v=temp(value)
        if now-timedelta(days=370)<=t<=now:
            merged[t.isoformat()]={'time':t.isoformat(),'temp':v};count+=1
    if not count:raise ValueError('No historical weather values')
    return {'source':'Open-Meteo','kind':'model_estimate','label':str(label)[:80],
            'fetched_at':now.isoformat(),'state':'ok',
            'current':{'time':stamp.isoformat(),'temp':current_temp},
            'hourly':[merged[k] for k in sorted(merged)]}


def refresh_weather(state):
    state=Path(state);config=Path(os.environ.get('HYDRO_WEATHER_CONFIG',str(state/'weather-config.json')))
    previous=load_weather(state)
    if not config.exists():return previous
    try:
        settings=json.loads(config.read_text());lat=float(settings['latitude']);lon=float(settings['longitude'])
        if not -90<=lat<=90 or not -180<=lon<=180:raise ValueError('Invalid location')
        query=urllib.parse.urlencode({'latitude':lat,'longitude':lon,'current':'temperature_2m',
          'hourly':'temperature_2m','past_days':2 if previous and previous.get('hourly') else 92,'forecast_days':1,'timezone':'UTC','timeformat':'unixtime'})
        request=urllib.request.Request('https://api.open-meteo.com/v1/forecast?'+query,headers={'User-Agent':'Hydro-Usage-Dashboard/1.0'})
        with urllib.request.urlopen(request,timeout=15) as response:
            data=response.read(1000001)
            if len(data)>1000000:raise ValueError('Oversized weather response')
            raw=json.loads(data)
        value=parse_response(raw,previous,settings.get('label','Outside'),datetime.now(timezone.utc))
        save(state/'weather-cache.json',value)
        return value
    except Exception:
        # Never suppress energy publication or advance a weather timestamp on failure.
        if previous:
            previous['state']='fetch_failed'
            try:save(state/'weather-cache.json',previous)
            except OSError:pass
            return previous
        value={'source':'Open-Meteo','kind':'model_estimate','state':'fetch_failed','hourly':[]}
        try:save(state/'weather-cache.json',value)
        except OSError:pass
        return value
