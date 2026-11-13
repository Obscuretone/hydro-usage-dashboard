"""Generate a private static dashboard from the cache; never export credentials."""
import argparse,json,math,sqlite3,shutil
from pathlib import Path
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo

def build(dbpath,out,assets):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(dbpath) as db:
  ids=[r[0] for r in db.execute('SELECT DISTINCT contract FROM hours')]
  if len(ids)!=1:raise ValueError('Expected one selected account cache; select explicitly before exporting multiple contracts.')
  key=ids[0];hours=[]
  for ts,kwh,temp,quality in db.execute('SELECT timestamp,kwh,temperature_c,quality FROM hours WHERE contract=? ORDER BY timestamp',(key,)):
   local=datetime.fromisoformat(ts).astimezone(ZoneInfo('America/Toronto'))
   hours.append({'time':local.isoformat(),'day':local.date().isoformat(),'hour':local.hour,'kwh':kwh,'temp':temp,'quality':quality})
  row=db.execute('SELECT payload FROM metadata WHERE contract=?',(key,)).fetchone()
  meta=json.loads(row[0]) if row else {}
 if not hours:raise ValueError('No readings; preserving the previous snapshot is preferable to publishing an empty dashboard.')
 expected={};day=date.fromisoformat(hours[0]['day']);end=date.fromisoformat(hours[-1]['day'])
 while day<=end:
  a=datetime.combine(day,datetime.min.time(),ZoneInfo('America/Toronto'));b=datetime.combine(day+timedelta(days=1),datetime.min.time(),ZoneInfo('America/Toronto'))
  expected[day.isoformat()]=int((b.astimezone(timezone.utc)-a.astimezone(timezone.utc)).total_seconds()/3600);day+=timedelta(days=1)
 payload={'generated':datetime.now(timezone.utc).isoformat(),'synced':meta.get('synced_at'),'rate':meta.get('rate'),'option':meta.get('option'),'hours':hours,'daily':meta.get('hydro_daily',[]),'periods':meta.get('billing_periods',[]),'expected':expected,'timezone':'America/Toronto'}
 (out/'data.json').write_text(json.dumps(payload,separators=(',',':'),allow_nan=False))
 for name in ['index.html','app.js','style.css','plotly.min.js']:shutil.copyfile(Path(assets)/name,out/name)
 return {'hours':len(hours),'daily_days':len(payload['daily']),'latest':hours[-1]['time'],'generated':payload['generated']}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--out',required=True);p.add_argument('--assets',required=True);a=p.parse_args()
 print(json.dumps(build(a.db,a.out,a.assets)))
