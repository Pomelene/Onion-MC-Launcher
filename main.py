"""Onion Minecraft Launcher entry point: Qt UI with the existing Python launcher services."""
import os
import sys
from pathlib import Path

dependencies=Path(__file__).resolve().parent/'.deps/qt'
if dependencies.is_dir():sys.path.insert(0,str(dependencies))
if '--self-check-output' in sys.argv or '--raster-check-output' in sys.argv:
    native='--raster-check-output' in sys.argv
    option='--raster-check-output' if native else '--self-check-output'
    os.environ['QT_QPA_PLATFORM']='windows' if native else 'offscreen'
    from launcher.qtui.selfcheck import run,run_raster
    sys.exit((run_raster if native else run)(sys.argv[sys.argv.index(option)+1]))
from launcher.qtui.app import main

if __name__=='__main__':sys.exit(main())
