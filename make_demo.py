"""Build a deterministic synthetic demo without a database or Hydro login."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from core import demo,daily
from deploy.build_snapshot import write_snapshot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',default='site')
    args=parser.parse_args();out=Path(args.out)
    if (out/'data.json').exists():
        previous=json.loads((out/'data.json').read_text())
        if any(row.get('quality')!='synthetic' for row in previous.get('hours',[])):
            raise ValueError('Use a separate directory for the demo; existing account readings were found.')
    frame=demo()
    normal_days=set(daily(frame).query('expected == 24').day)
    frame=frame[frame.timestamp.dt.date.isin(normal_days)]
    summaries=daily(frame)
    hours=[{'time':row.timestamp.isoformat(),'day':row.timestamp.date().isoformat(),
            'hour':row.timestamp.hour,'kwh':row.kwh,'temp':row.temperature_c,'quality':'synthetic'}
           for row in frame.itertuples()]
    meta={'synced_at':datetime.now(timezone.utc).isoformat(),
          'hydro_daily':[{'dateJourConso':row.day.isoformat(),'consoTotalQuot':row.kwh,
                          'tempMoyenneQuot':row.temperature_c,'codeConsoQuot':'synthetic'}
                         for row in summaries.itertuples()]}
    print('Synthetic demo only:',write_snapshot(hours,meta,out,Path(__file__).parent/'deploy/assets'))


if __name__=='__main__':main()
