"""Short-lived mobile sync, visible failures, and atomic static publication."""
from pathlib import Path
import argparse,datetime,json,os,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
STATE=Path('data/account').resolve();PUBLIC=Path('site').resolve()
STATUS=STATE/'refresh-status.json'
sys.path.insert(0,str(ROOT))
from deploy.build_snapshot import build


def read_status():
    try:
        value=json.loads(STATUS.read_text())
        return value if isinstance(value,dict) else {}
    except (FileNotFoundError,ValueError):
        return {}


def write_status(status):
    fd,name=tempfile.mkstemp(prefix='.refresh-status-',dir=STATE)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(status,stream,allow_nan=False)
            stream.flush();os.fsync(stream.fileno())
        temporary.replace(STATUS)
    finally:
        temporary.unlink(missing_ok=True)


def publish(status):
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=PUBLIC/stamp
    try:
        info=build(out,ROOT/'deploy/assets',status=status)
        for p in out.rglob('*'):
            if p.is_file():p.chmod(0o640)
        out.chmod(0o750)
        tmp=PUBLIC/'current.next'
        tmp.unlink(missing_ok=True);tmp.symlink_to(out);tmp.replace(PUBLIC/'current')
        keep=sorted([p for p in PUBLIC.iterdir() if p.is_dir() and not p.is_symlink()],reverse=True)
        for old in keep[3:]:shutil.rmtree(old)
        print('Published snapshot:',info,flush=True)
    except Exception:
        if out.exists():shutil.rmtree(out)
        raise


def main():
    status=read_status()
    result=0
    if '--publish-only' not in sys.argv and '--skip-sync' not in sys.argv:
        status['last_attempt_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            completed=subprocess.run(
                [sys.executable,str(ROOT/'sync.py'),'--auth-client','mobile',
                 '--use-session','--days','3','--data-dir',str(STATE)],
                cwd=ROOT,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=240)
            result=completed.returncode
        except (subprocess.TimeoutExpired,OSError):
            result=1
        status['state']='ok' if result==0 else 'sign_in_required' if result==20 else 'sync_failed'
        if result==0:
            status['last_success_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_status(status)
    # A failed sync publishes the cached readings with an explicit failure state.
    # Failure to build leaves the previous snapshot untouched.
    publish(status)
    if result:
        print('Refresh incomplete:',status.get('state'),flush=True)
        raise SystemExit(result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',required=True)
    parser.add_argument('--publish-dir',required=True)
    parser.add_argument('--skip-sync','--publish-only',action='store_true')
    args=parser.parse_args()
    STATE=Path(args.data_dir).resolve();STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    PUBLIC=Path(args.publish_dir).resolve();PUBLIC.mkdir(parents=True,exist_ok=True)
    STATUS=STATE/'refresh-status.json'
    main()
