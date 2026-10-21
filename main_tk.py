# -*- coding: utf-8 -*-
"""CraftBridge 启动器入口（图形界面）。

运行：python main.py
"""

import sys

from launcher.ui.dpi import enable_high_dpi
enable_high_dpi()

from launcher.ui.app import main


if __name__ == "__main__":
    sys.exit(main() or 0)
