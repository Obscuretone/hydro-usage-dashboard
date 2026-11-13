"""Generate deterministic synthetic readings; never reads a Hydro account."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from core import Cache, daily, demo
from deploy.build_snapshot import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default='data/demo')
    parser.add_argument('--out', default='site')
    args = parser.parse_args()
    path = Path(args.data_dir) / 'hydro.sqlite'
    cache = Cache(path)
    if set(cache.contracts()) - {'synthetic-demo'}:
        raise ValueError('Use an empty directory for synthetic data.')
    frame = demo()
    # Match the live importer's deliberate DST gaps in the local-hour graph.
    normal_days = set(daily(frame).query('expected == 24').day)
    frame = frame[frame.timestamp.dt.date.isin(normal_days)]
    with cache.connect() as db:
        db.execute('DELETE FROM hours WHERE contract = ?', ('synthetic-demo',))
    cache.upsert('synthetic-demo', frame)
    summaries = daily(cache.load('synthetic-demo'))
    cache.metadata('synthetic-demo', {
        'synced_at': datetime.now(timezone.utc).isoformat(),
        'hydro_daily': [
            {'dateJourConso': row.day.isoformat(), 'consoTotalQuot': row.kwh,
             'tempMoyenneQuot': row.temperature_c, 'codeConsoQuot': 'synthetic'}
            for row in summaries.itertuples()
        ],
    })
    result = build(path, args.out, Path(__file__).parent / 'deploy/assets')
    print('Synthetic demo only:', result)


if __name__ == '__main__':
    main()
