"""Export a private static snapshot without contract IDs or credentials."""
import argparse,json,shutil,sys
from pathlib import Path
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deploy.hydro_store import connect


def write_snapshot(hours,meta,out,assets,status=None):
    if not hours:
        raise ValueError('No readings; preserve the previous snapshot.')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    expected={};day=date.fromisoformat(hours[0]['day']);end=date.fromisoformat(hours[-1]['day'])
    while day<=end:
        a=datetime.combine(day,datetime.min.time(),ZoneInfo('America/Toronto'))
        b=datetime.combine(day+timedelta(days=1),datetime.min.time(),ZoneInfo('America/Toronto'))
        expected[day.isoformat()]=int((b.astimezone(timezone.utc)-a.astimezone(timezone.utc)).total_seconds()/3600)
        day+=timedelta(days=1)
    payload={'generated':datetime.now(timezone.utc).isoformat(),'synced':meta.get('synced_at'),
             'rate':meta.get('rate'),'option':meta.get('option'),'hours':hours,
             'daily':meta.get('hydro_daily',[]),'periods':meta.get('billing_periods',[]),
             'expected':expected,'timezone':'America/Toronto'}
    if status:
        payload['refresh']={k:status.get(k) for k in ['state','last_attempt_at','last_success_at']}
    (out/'data.json').write_text(json.dumps(payload,separators=(',',':'),allow_nan=False))
    for name in ['index.html','app.js','style.css','plotly.min.js']:
        shutil.copyfile(Path(assets)/name,out/name)
    return {'hours':len(hours),'daily_days':len(payload['daily']),
            'latest':hours[-1]['time'],'generated':payload['generated']}


def build(out,assets,status=None):
    with connect() as connection,connection.cursor() as db:
        db.execute('SELECT DISTINCT contract FROM hours')
        ids=[r[0] for r in db]
        if len(ids)!=1:
            raise ValueError('Expected one selected account cache; isolate multiple contracts before export.')
        key=ids[0];hours=[]
        db.execute('SELECT timestamp,kwh,temperature_c,quality FROM hours WHERE contract=%s ORDER BY timestamp',(key,))
        for ts,kwh,temp,quality in db:
            local=datetime.fromisoformat(ts).astimezone(ZoneInfo('America/Toronto'))
            hours.append({'time':local.isoformat(),'day':local.date().isoformat(),
                          'hour':local.hour,'kwh':kwh,'temp':temp,'quality':quality})
        db.execute('SELECT payload FROM metadata WHERE contract=%s',(key,))
        row=db.fetchone();meta=json.loads(row[0]) if row else {}
    return write_snapshot(hours,meta,out,assets,status)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True);p.add_argument('--assets',required=True)
    args=p.parse_args();print(json.dumps(build(args.out,args.assets)))
