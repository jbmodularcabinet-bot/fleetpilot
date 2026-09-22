"""Package a verified web build, not an independently editable source copy."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = Path('/mnt/c/Users/User/Documents/ChatGPT/FleetPilot')


def main():
    build = ROOT / 'apps/web/.next'
    build_id = (build / 'BUILD_ID').read_text().strip()
    standalone = build / 'standalone/apps/web/server.js'
    if not standalone.is_file():
        raise SystemExit('Verified standalone server entry is missing')
    if (ROOT / 'package-lock.json').read_bytes() != (WINDOWS / 'package-lock.json').read_bytes():
        raise SystemExit('Existing Windows dependencies do not match the locked build dependencies')
    files = [p for p in build.rglob('*') if p.is_file() and not any(x in p.relative_to(build).parts for x in ('cache','standalone','node_modules'))]
    needed = sum(p.stat().st_size for p in files)
    if shutil.disk_usage(WINDOWS).free < needed + 800000000:
        raise SystemExit('Insufficient host reserve for the bounded demo artifact')
    destination = WINDOWS / '.runtime/mvp1-demo-artifacts' / build_id
    if destination.exists():
        raise SystemExit('Artifact already exists; refusing overwrite')
    destination.mkdir(parents=True)
    for p in files:
        target = destination / '.next' / p.relative_to(build)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p,target)
    shutil.copytree(ROOT/'apps/web/public',destination/'public')
    shutil.copy2(standalone,destination/'server.js')
    shutil.copy2(ROOT/'apps/web/package.json',destination/'package.json')
    manifest = {'source':str(ROOT),'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_state':'Uncommitted candidate; not production-certified','build_id':build_id,
        'lock_sha256':hashlib.sha256((ROOT/'package-lock.json').read_bytes()).hexdigest(),
        'artifact_bytes':needed,'runtime':'Windows Node with existing Windows lock-matched dependencies; no Linux node_modules copied',
        'files':{str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}}
    (destination/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2))
    (ROOT/'.runtime/batch16/demo-web-artifact.json').write_text(json.dumps({'linux_artifact_path':str(destination),'windows_artifact_path':str(destination).replace('/mnt/c/','C:/'),'build_id':build_id},indent=2))
    print(json.dumps({'build_id':build_id,'artifact_bytes':needed,'destination':str(destination),'native_dependencies_copied':False}))


if __name__=='__main__':
    main()
