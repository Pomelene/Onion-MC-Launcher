"""Onion Minecraft Launcher entry point: Qt UI with the existing Python launcher services."""
import os
import sys
from pathlib import Path

dependencies=Path(__file__).resolve().parent/'.deps/qt'
if dependencies.is_dir():sys.path.insert(0,str(dependencies))
pillow=Path(__file__).resolve().parent/'.deps/pillow'
if pillow.is_dir():sys.path.insert(0,str(pillow))
if '--self-check-output' in sys.argv:
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from launcher.qtui.selfcheck import run
    sys.exit(run(sys.argv[sys.argv.index('--self-check-output')+1]))
from launcher.qtui.app import main

if __name__=='__main__':sys.exit(main())
