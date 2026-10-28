"""Exercise the real onefile bootloader with an expired inherited runtime."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import argparse
from dataclasses import replace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launcher.updates import replacement_script,updated_executable_path,_ps
from tests.test_launcher_updates import release

def check_launcher(path,versioned=False,filename=None):
    """Replace and restart a disposable copy of an actual release executable."""
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='launcher-update-') as temporary:
        root=Path(temporary);exe=root/(filename or ("自定义 [Onion] '重命名' v0.3.0.1-T.exe" if versioned else "自定义 [Onion] '重命名'.exe"));staged=root/'.onion/updates/pending-check/update.exe'
        staged.parent.mkdir(parents=True);shutil.copy2(path,exe);shutil.copy2(path,staged)
        settings=root/'onionmcl.json';settings.write_text('{"preserve":"fixture"}');original=settings.read_bytes()
        report=root/'startup.json'
        item=replace(release(),size=staged.stat().st_size,sha256=hashlib.sha256(staged.read_bytes()).hexdigest())
        script=replacement_script(exe,staged,item,2147483647)
        script=script.replace('$info.FileName=$target','$info.FileName=$target\n    $info.Arguments='+_ps('--startup-check-output "'+str(report)+'"'))
        dirty={**os.environ,'_PYI_ARCHIVE_FILE':str(exe),'_PYI_APPLICATION_HOME_DIR':str(root/'deleted-runtime'),'_PYI_PARENT_PROCESS_LEVEL':'1'}
        dirty.pop('PYINSTALLER_RESET_ENVIRONMENT',None)
        powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        result=subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-EncodedCommand',encoded],env=dirty,capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode==0,result.stderr.decode(errors='replace')
        deadline=time.monotonic()+30
        while not report.exists() and time.monotonic()<deadline:time.sleep(.05)
        assert json.loads(report.read_text())['result']=='pass'
        assert settings.read_bytes()==original
        destination=updated_executable_path(exe,item.version)
        assert hashlib.sha256(destination.read_bytes()).hexdigest()==item.sha256
        if destination!=exe:assert not exe.exists()
        assert json.loads((staged.parent/'result.json').read_text())['result']=='success'
        print('PASS: actual launcher update, renamed target, inherited runtime reset and isolated real-entry startup')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--launcher',type=Path);args=parser.parse_args()
    if os.name!='nt':raise SystemExit('Windows only')
    if args.launcher:return check_launcher(args.launcher.resolve())
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='frozen-restart-') as temporary:
        root=Path(temporary)
        source=root/'probe.py'
        source.write_text("import json,sys\nfrom pathlib import Path\nPath(sys.executable).with_suffix('.json').write_text(json.dumps({'runtime':sys._MEIPASS}))\n",encoding='utf-8')
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--console','--distpath',str(root/'dist'),'--workpath',str(root/'build'),'--specpath',str(root),str(source)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        exe=root/"自定义 [Onion] '测试'.exe"
        shutil.copy2(root/'dist/probe.exe',exe)
        dirty={**os.environ,'_PYI_ARCHIVE_FILE':str(exe),'_PYI_APPLICATION_HOME_DIR':str(root/'deleted-runtime'),'_PYI_PARENT_PROCESS_LEVEL':'1'}
        dirty.pop('PYINSTALLER_RESET_ENVIRONMENT',None)
        broken=subprocess.run([str(exe)],env=dirty,capture_output=True,timeout=20)
        assert broken.returncode!=0 and not exe.with_suffix('.json').exists(),'Expected stale-runtime bootloader failure'
        print('PASS: reproduced old restart failure with expired onefile runtime',flush=True)
        staged=root/'.onion/updates/pending-probe/update.exe'
        staged.parent.mkdir(parents=True)
        shutil.copy2(exe,staged)
        item=replace(release(),size=staged.stat().st_size,sha256=hashlib.sha256(staged.read_bytes()).hexdigest())
        powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        script=replacement_script(exe,staged,item,2147483647)
        encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        result=subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-EncodedCommand',encoded],env=dirty,capture_output=True,timeout=40)
        assert result.returncode==0,result.stderr.decode(errors='replace')
        assert json.loads((staged.parent/'result.json').read_text())['result']=='success'
        assert json.loads(exe.with_suffix('.json').read_text())['runtime']!=dirty['_PYI_APPLICATION_HOME_DIR']
        print('PASS: real updater starts a fresh onefile runtime despite inherited stale environment')

if __name__=='__main__':main()
