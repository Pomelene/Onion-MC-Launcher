"""User-assisted live verification. Tokens never appear in stdout or reports.

Run explicitly: python -X utf8 scripts/verify_microsoft_live.py
The user authorizes the displayed code on Microsoft's own page. No password is
handled here. The account is saved to the published launcher's store only after
both initial profile retrieval and an immediate refresh have succeeded.
"""
import datetime
import json
import sys
import threading
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher.auth.microsoft import login_with_device_code,refresh_minecraft,AuthError
from launcher.auth.application import resolve_client_id
from launcher.config import Config
from launcher.accounts import AccountStore,AccountRecord


def main():
    config=Config(ROOT/'dist/config/settings.json');client_id=resolve_client_id(config)
    report={'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'result':'waiting_for_user_authorization','live_network':True,
            'application_name':'Onion Minecraft Launcher',
            'password_handled':False,'tokens_logged':False,'account_saved':False,'stages':[]}
    report_path=ROOT/'docs/microsoft-live-check.json'
    cancel=threading.Event()
    def save_report():
        temporary=report_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(report_path)
    def step(message):
        report['stages'].append(message);save_report()
        print(json.dumps({'stage':message},ensure_ascii=False),flush=True)
    def code_received(code):
        # Only the short user-facing authorization code is displayed. The private
        # device_code stays in memory; neither code is written to the report.
        print(json.dumps({'action':'authorize_on_microsoft','url':code.verification_uri,
                          'user_code':code.user_code,'expires_in':code.expires_in},ensure_ascii=False),flush=True)
    save_report()
    try:
        data=login_with_device_code(client_id,code_received,cancel.is_set,step)
        report['initial_profile_verified']=True
        step('正在真机验证账号续期')
        refreshed=refresh_minecraft(client_id,data['refresh_token'])
        if refreshed['uuid']!=data['uuid']:raise AuthError('续期后的账号身份不一致',code='identity_mismatch')
        data.update(refreshed);data['client_id']=client_id
        # Reload at the last moment to retain existing accounts in the store.
        store=AccountStore(ROOT/'dist/config/accounts.json')
        account=AccountRecord(type='microsoft',user_type='msa',**data)
        store.add(account);store.set_current(account.uuid)
        reloaded=AccountStore(store.path).get(account.uuid)
        assert reloaded and reloaded.access_token==account.access_token and reloaded.client_id==client_id
        report.update(result='pass',refresh_verified=True,account_saved=True,persisted_record_verified=True,
                      player_profile_verified=True,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        save_report();print(json.dumps({'result':'pass','account_saved':True,'refresh_verified':True}),flush=True)
        return 0
    except AuthError as error:
        report.update(result='failed',error=str(error),error_code=error.code,http_status=error.status)
        save_report();print(json.dumps({'result':'failed','error':str(error),'code':error.code,'http_status':error.status},ensure_ascii=False),flush=True)
        return 1
    except KeyboardInterrupt:
        cancel.set();report['result']='cancelled';save_report();return 130
    except Exception as error:
        report.update(result='failed',error_type=type(error).__name__)
        save_report();print(json.dumps({'result':'failed','error_type':type(error).__name__}),flush=True)
        return 1


if __name__=='__main__':sys.exit(main())
