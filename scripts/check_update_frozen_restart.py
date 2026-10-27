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
from dataclasses import replace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launcher.updates import replacement_script
from tests.test_launcher_updates import release

def main():
    if os.name!='nt':raise SystemExit('Windows only')
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
