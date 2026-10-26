"""Run the real Windows updater against disposable silent fixture programs."""
import base64,hashlib,json,os,subprocess,sys,tempfile
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from launcher.updates import replacement_script,verify_executable
from tests.test_launcher_updates import release

if os.name!='nt':raise SystemExit('Windows-only replacement check')
system=Path(os.environ['SystemRoot'])
powershell=system/'System32/WindowsPowerShell/v1.0/powershell.exe'
compiler=system/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
assert compiler.is_file(),'Windows .NET fixture compiler unavailable'

def compile_fixture(target,marker,code):
    target.parent.mkdir(parents=True,exist_ok=True);source=target.with_suffix('.cs')
    escaped=str(marker).replace('"','""')
    source.write_text('class Fixture { static void Main() { System.IO.File.WriteAllText(@"'+escaped+'", "'+('old' if code==0 else 'new')+'"); System.Environment.Exit('+str(max(0,code))+'); } }',encoding='utf-8-sig')
    subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64','/out:'+str(target),str(source)],check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    source.unlink()

with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='replacement-') as temporary:
    for scenario in ('success','tampered','startup-failed'):
        root=Path(temporary)/(scenario+" 中文 [TARGET] 'STAGED' $()")
        original=root/'Onion.exe';staged=root/'.onion/updates/pending-fixture/update.exe';marker=root/'launched.txt'
        compile_fixture(original,marker,0);before=original.read_bytes()
        compile_fixture(staged,marker,17 if scenario=='startup-failed' else -1)
        item=replace(release(),size=staged.stat().st_size,sha256=hashlib.sha256(staged.read_bytes()).hexdigest())
        verify_executable(staged,item)
        settings=root/'onionmcl.json';settings.write_text('{"fixture":"preserve"}');settings_before=settings.read_bytes()
        parent=subprocess.Popen([str(powershell),'-NoProfile','-NonInteractive','-Command','Start-Sleep -Milliseconds 600'],creationflags=subprocess.CREATE_NO_WINDOW)
        script=replacement_script(original,staged,item,parent.pid)
        if scenario=='tampered':staged.write_bytes(staged.read_bytes()+b'tampered')
        encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        finished=subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand',encoded],timeout=30,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        parent.wait(timeout=5)
        assert settings.read_bytes()==settings_before
        state=json.loads((staged.parent/'result.json').read_text())
        if scenario=='success':
            assert finished.returncode==0 and state['result']=='success',(staged.parent/'error.txt').read_text(encoding='utf-8') if (staged.parent/'error.txt').is_file() else finished.stderr.decode(errors='replace')
            assert hashlib.sha256(original.read_bytes()).hexdigest()==item.sha256
            assert (staged.parent/'previous.exe').read_bytes()==before
        else:
            assert finished.returncode!=0 and state['result']=='failed'
            assert original.read_bytes()==before,(staged.parent/'rollback-error.txt').read_text(encoding='utf-8') if (staged.parent/'rollback-error.txt').is_file() else 'Rollback mismatch'
        print('PASS:',scenario,'with Unicode, brackets, apostrophes, parent wait and settings preservation')
print('PASS: actual Windows atomic replacement, corruption rejection and startup-failure rollback')
