"""Build local seed-map DLL using a project-local Zig C compiler."""
from pathlib import Path
import subprocess
import os

root=Path(__file__).resolve().parents[1]
compiler=root/'.deps/buildtools/ziglang/zig.exe'
if not compiler.exists(): raise SystemExit('Install: python -m pip install --target .deps/buildtools ziglang==0.16.0')
source=root/'launcher/native'
output=root/'assets/native/onion_seedmap.dll';output.parent.mkdir(parents=True,exist_ok=True)
env=os.environ.copy();env['ZIG_GLOBAL_CACHE_DIR']=str(root/'tmp/zig-cache')
temporary=root/'tmp/zig-temp';temporary.mkdir(parents=True,exist_ok=True)
env['TEMP']=env['TMP']=str(temporary)
units=['generator','layers','biomenoise','biomes','noise','util','finders','quadbase',
       'terrainnoise','carver','xradv','features/abandoned_camp','features/end_city',
       'features/fortress','features/ore','features/stronghold']
cmd=[str(compiler),'cc','-shared','-O2','-fwrapv','-target','x86_64-windows-gnu',
     str(source/'seedmap.c'),*[str(source/f'cubiomes/{unit}.c') for unit in units],
     '-o',str(output)]
subprocess.run(cmd,cwd=root,env=env,check=True)
print(output,output.stat().st_size)
