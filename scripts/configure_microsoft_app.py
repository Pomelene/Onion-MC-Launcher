"""Install the publisher's public Microsoft application ID; no secret required.

Usage: python scripts/configure_microsoft_app.py APPLICATION_ID
Updates only the public app manifest and microsoft_client_id in existing launcher
settings. Run scripts/build_qt.ps1 afterwards to ship the identity in the EXE.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher.auth.application import valid_client_id
from launcher.config import Config
from launcher.paths import LAUNCHER_NAME


def main():
    parser=argparse.ArgumentParser(description='Configure the public Onion Microsoft application ID')
    parser.add_argument('application_id');args=parser.parse_args()
    if not valid_client_id(args.application_id):parser.error('Expected a valid nonzero application UUID, not a client secret')
    manifest=ROOT/'assets/microsoft-app.json'
    data={'client_id':args.application_id.strip(),'display_name':LAUNCHER_NAME,'source':'publisher-owned Microsoft application'}
    temporary=manifest.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(manifest)
    for relative in ('config/settings.json','dist/config/settings.json','dist/qt/config/settings.json'):
        path=ROOT/relative
        if path.exists():Config(path).set('microsoft_client_id',args.application_id.strip())
    print('Onion Microsoft application configured. Rebuild the executable to bundle it.')


if __name__=='__main__':main()
