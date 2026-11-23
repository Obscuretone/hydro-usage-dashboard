"""Strict hourly storage and deliberately conservative household analysis."""
import io
import math
from datetime import date, timedelta
import numpy as np
import pandas as pd

from deploy.hydro_store import connect

TZ = 'America/Toronto'


def normalize(frame):
    if not {'timestamp', 'kwh'} <= set(frame.columns):
        raise ValueError('Required CSV columns: timestamp,kwh. Optional: temperature_c,quality.')
    rows = []
    for row in frame.to_dict('records'):
        ts = pd.Timestamp(row['timestamp'])
        if ts.tzinfo is None:
            raise ValueError('Every timestamp needs an explicit UTC offset; local ambiguous hours are unsafe.')
        ts = ts.tz_convert('UTC')
        if ts.minute or ts.second or ts.microsecond:
            raise ValueError('Use hourly interval START timestamps on the hour.')
        kwh = float(row['kwh'])
        if not math.isfinite(kwh) or kwh < 0:
            raise ValueError('kWh must be finite and nonnegative; missing hours must be omitted, not zero-filled.')
        temp = row.get('temperature_c')
        temp = None if pd.isna(temp) else float(temp)
        if temp is not None and (not math.isfinite(temp) or not -80 <= temp <= 60):
            raise ValueError('Invalid temperature.')
        quality = row.get('quality', 'unknown')
        quality = 'unknown' if pd.isna(quality) else str(quality)
        rows.append((ts.isoformat(), kwh, temp, quality))
    result = pd.DataFrame(rows, columns=['timestamp','kwh','temperature_c','quality'])
    if result.timestamp.duplicated().any():
        raise ValueError('Duplicate instants in import: resolve conflicting readings before importing.')
    return result


class Cache:
    def upsert(self, contract, frame):
        clean = normalize(frame)
        rows = [(contract, timestamp, kwh, None if pd.isna(temp) else temp, quality)
                for timestamp, kwh, temp, quality in clean.itertuples(index=False, name=None)]
        with connect() as connection, connection.cursor() as db:
            db.executemany('INSERT INTO hours VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE '
                           'kwh=VALUES(kwh), temperature_c=VALUES(temperature_c), quality=VALUES(quality)',
                           rows)
            connection.commit()
        return len(clean)
    def load(self, contract):
        with connect() as connection, connection.cursor() as db:
            columns = ['timestamp', 'kwh', 'temperature_c', 'quality']
            db.execute('SELECT timestamp,kwh,temperature_c,quality FROM hours WHERE contract=%s ORDER BY timestamp', (contract,))
            f = pd.DataFrame(db.fetchall(), columns=columns)
        f.timestamp = pd.to_datetime(f.timestamp, utc=True).dt.tz_convert(TZ)
        return f
    def contracts(self):
        with connect() as connection, connection.cursor() as db:
            db.execute('SELECT DISTINCT contract FROM hours ORDER BY contract')
            return [r[0] for r in db]
    def metadata(self, contract, payload=None):
        import json
        with connect() as connection, connection.cursor() as db:
            if payload is not None:
                db.execute('INSERT INTO metadata VALUES (%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload)',
                           (contract,json.dumps(payload)))
                connection.commit()
            db.execute('SELECT payload FROM metadata WHERE contract=%s',(contract,))
            row = db.fetchone()
        return json.loads(row[0]) if row else {}


def daily(frame):
    if frame.empty:
        return pd.DataFrame(columns=['day','kwh','hours','temperature_c','expected','complete'])
    f = frame.copy(); f['day'] = f.timestamp.dt.date
    f['source_flagged'] = f.quality.astype(str).str.contains('day_flagged') if 'quality' in f else False
    d = f.groupby('day').agg(kwh=('kwh','sum'),hours=('kwh','count'),temperature_c=('temperature_c','mean'),source_flagged=('source_flagged','any')).reset_index()
    d['expected'] = [int((pd.Timestamp(x+timedelta(days=1),tz=TZ).tz_convert('UTC')-pd.Timestamp(x,tz=TZ).tz_convert('UTC')).total_seconds()/3600) for x in d.day]
    d['complete'] = (d.hours == d.expected) & ~d.source_flagged
    return d


def rate_d(kwh, days, start, end, rate='D'):
    """One ordinary low-voltage Rate D period, before taxes/credits/adjustments."""
    if rate != 'D':
        raise ValueError('Only ordinary Rate D without an option is modeled.')
    if start < date(2026,4,1) or end >= date(2027,4,1):
        raise ValueError('This rate table is limited to April 2026–March 2027. Split other periods and verify rates.')
    if days <= 0 or end < start or days != (end-start).days+1 or not math.isfinite(kwh) or kwh < 0:
        raise ValueError('Invalid inclusive billing period or consumption.')
    low = min(kwh,40*days); high = max(0,kwh-low)
    return dict(access=days*.46154, first=low*.07065, second=high*.11142,
                total=days*.46154+low*.07065+high*.11142, high_kwh=high)


def heating_fit(d, base=18):
    d = d[d.complete & d.temperature_c.notna()].copy()
    if len(d) < 14:
        return None
    x = np.maximum(0,base-d.temperature_c.to_numpy()); y = d.kwh.to_numpy()
    if np.ptp(x) < 5:
        return None
    slope, intercept = np.polyfit(x,y,1)
    pred = intercept+slope*x
    r2 = 1-np.sum((y-pred)**2)/np.sum((y-y.mean())**2) if np.var(y)>0 else 0
    return dict(slope=float(slope),intercept=float(intercept),r2=float(r2),days=len(d),
                heating_kwh=float(max(0,slope)*x.sum()),data=d.assign(hdd=x,predicted=pred))


def unusual(frame):
    f = frame.copy(); f['hour'] = f.timestamp.dt.hour
    group = f.groupby('hour').kwh
    f['typical'] = group.transform('median')
    f['mad'] = group.transform(lambda v: (v-v.median()).abs().median())
    f['excess_kwh'] = f.kwh-f.typical
    # A floor prevents tiny household variability from producing alarm flags.
    f['flag'] = (group.transform('count') >= 7) & (f.excess_kwh > np.maximum(1,4*1.4826*f.mad))
    return f[f.flag].sort_values('excess_kwh',ascending=False)


def demo():
    """Seeded synthetic home: electric heat, persistent load and deliberate spikes."""
    rng = np.random.default_rng(412)
    ts = pd.date_range('2026-08-14', '2026-11-12',freq='h',inclusive='left',tz=TZ)
    day = (ts.tz_convert('UTC')-ts[0].tz_convert('UTC')).total_seconds()/86400
    temp = 21-day*.25+4*np.sin(day/5)
    kwh = .95+np.maximum(0,18-temp)*.12+np.where((ts.hour>=17)&(ts.hour<=20),.9,0)+rng.uniform(0,.15,len(ts))
    kwh = kwh+np.where((ts.day%13==0)&(ts.hour==2),5,0)
    return pd.DataFrame({'timestamp':ts,'kwh':np.round(kwh,3),'temperature_c':np.round(temp,1),'quality':'synthetic'})


def parse_hourly(payload, wanted):
    """Parse v4.4 JSON; fail closed if the API hour semantics are unfamiliar.

    The unqualified hour JSON cannot safely distinguish fall-back folds. DST
    transition days are explicitly left as gaps; offset CSV can fill them.
    """
    if payload.get('success') is not True:
        raise ValueError('Hydro did not return a successful hourly response.')
    result = payload['results']
    day_flagged = bool(result.get('indErreurJourneeEnergie'))
    begin=pd.Timestamp(wanted,tz=TZ); finish=pd.Timestamp(wanted+timedelta(days=1),tz=TZ)
    if (finish.tz_convert('UTC')-begin.tz_convert('UTC')).total_seconds()!=86400:
        raise ValueError('DST transition day needs offset-aware CSV; left as a gap.')
    rows=[]
    for r in result['listeDonneesConsoEnergieHoraire']:
        if r.get('consoTotal') is None:
            continue
        label=str(r['heure'])
        # Hydro hour field is treated as interval-start only for 0..23 / HH:00.
        import re
        if not re.fullmatch(r'(?:[01]?\d|2[0-3])(?::00(?::00)?)?',label):
            raise ValueError('Unknown hour label; inspect locally before mapping it.')
        hour=int(label.split(':')[0])
        rows.append(dict(timestamp=begin+pd.Timedelta(hours=hour),kwh=r['consoTotal'],quality=str(r.get('codeConso','unknown')) + (';day_flagged' if day_flagged else '')))
    return normalize(pd.DataFrame(rows,columns=['timestamp','kwh','quality']))


def portal_daily(records):
    """Validate portal daily totals separately from derived hourly totals."""
    rows=[]
    for r in records:
        kwh=r.get('consoTotalQuot'); temp=r.get('tempMoyenneQuot')
        if kwh is None:
            continue
        kwh=float(kwh)
        if not math.isfinite(kwh) or kwh<0:
            continue
        temp=float(temp) if temp is not None else np.nan
        if not math.isfinite(temp) or not -80<=temp<=60:
            temp=np.nan
        quality=str(r.get('codeConsoQuot','unknown'))
        rows.append({'day':date.fromisoformat(str(r['dateJourConso'])[:10]),'kwh':kwh,'temperature_c':temp,'quality':quality,'complete':quality=='R'})
    f=pd.DataFrame(rows,columns=['day','kwh','temperature_c','quality','complete'])
    if f.day.duplicated().any():
        raise ValueError('Duplicate portal daily dates; resolve before analysis.')
    return f.sort_values('day')
