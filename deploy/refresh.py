"""One-shot sync and atomic static publication; schedule hourly with cron."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from build_snapshot import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--publish-dir', required=True,
                        help='Private publication directory; serve its current/ symlink')
    parser.add_argument('--days', type=int, choices=range(1, 733), default=3)
    parser.add_argument('--skip-sync', action='store_true', help='Export the existing cache only')
    args = parser.parse_args()
    source = Path(__file__).resolve().parent.parent
    data = Path(args.data_dir).resolve()
    publish = Path(args.publish_dir).resolve()
    if not args.skip_sync:
        subprocess.run([sys.executable, str(source / 'sync.py'), '--use-session',
                        '--data-dir', str(data), '--days', str(args.days)],
                       check=True, stdin=subprocess.DEVNULL)
    publish.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='snapshot-', dir=publish))
    link = publish / ('.current-' + staging.name)
    try:
        result = build(data / 'hydro.sqlite', staging, source / 'deploy/assets')
        staging.chmod(0o755)  # Allow the static web-server user to traverse the snapshot.
        link.symlink_to(staging.name, target_is_directory=True)
        os.replace(link, publish / 'current')
    except BaseException:
        link.unlink(missing_ok=True)
        shutil.rmtree(staging)
        raise
    # Keep the current snapshot plus two predecessors; the served link never gaps.
    snapshots = sorted(publish.glob('snapshot-*'), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in snapshots[3:]:
        if old.is_dir() and old != staging:
            shutil.rmtree(old)
    print(result)


if __name__ == '__main__':
    main()
