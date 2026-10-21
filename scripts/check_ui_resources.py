"""Construct the real UI withdrawn, with disposable empty-library configuration.
No desktop input, screenshots, Minecraft processes or user game data are used.
"""
import json
import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from launcher.ui.dpi import enable_high_dpi,px
enable_high_dpi()
import tkinter as tk
from launcher.config import Config
from launcher.ui.app import App
from launcher.ui.icons import PATHS,raster

root_dir=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(dir=root_dir/'tmp',prefix='ui-empty-') as location:
    base=Path(location)
    settings=base/'config/settings.json'
    cfg=Config(settings)
    cfg.set('game_dir',str(base/'empty-game'))
    cfg.set('theme_preset','bridge')
    original_init=tk.Tk.__init__
    def hidden_init(self,*args,**kwargs):
        original_init(self,*args,**kwargs)
        self.withdraw()
    errors=[]
    with patch.object(tk.Tk,'__init__',hidden_init), patch('launcher.ui.app.default_settings_path',return_value=settings), patch('launcher.ui.app.default_accounts_path',return_value=base/'accounts.json'), patch('launcher.ui.app.app_root',return_value=base):
        app=App()
        app.report_callback_exception=lambda *exc: errors.append(str(exc))
        app.update_idletasks()
        assert app.state()=='withdrawn'
        assert app.version_var.get()=='尚未安装游戏'
        assert str(app.version_combo.cget('state'))=='disabled'
        assert app.header_launch._text=='安装游戏'
        assert app.header_launch._icon_name=='download'
        assert app.account_name.cget('text')=='添加游戏账号'
        settings_page = app.pages['settings']
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        game_entry = next(widget for widget in descendants(settings_page)
                          if isinstance(widget, tk.Entry) and
                          str(widget.cget('textvariable')) == str(settings_page._vars['game_dir']))
        holder = game_entry.master
        assert holder.pack_info()['in'] != holder.master, 'settings control escaped its row'
        # Exercise rebuilt default/empty pages without starting downloads.
        for page in ('versions','mods','worlds','logs','settings','home'):
            app.switch_page(page)
            app.update_idletasks()
        button=app.header_launch
        calls=[]
        button.configure(command=lambda:calls.append('clicked'),state='disabled')
        button.invoke()
        assert calls==[]
        button.configure(state='normal')
        button.invoke()
        assert calls==['clicked']
        for mode in ('light','dark'):
            app.config_obj.set('theme_preset','bridge' if mode=='light' else 'deep-ocean')
            app.apply_theme()
            app.update_idletasks()
        assert not errors,errors
        app.destroy()
    for icon in PATHS:
        for size in (16,24,32,48):
            pic=raster(icon,'#176bce',size)
            assert pic.size==(size,size) and pic.getbbox(),icon
    report={'result':'pass','visible_windows_created':False,'empty_library':True,'empty_account':True,'page_construction':['home','versions','download','mods','worlds','logs','settings'],'themes':['bridge','deep-ocean'],'disabled_button':True,'icons':len(PATHS),'dpi_scale':px(100)/100,'visual_review':'pending'}
    (root_dir/'docs/ui-resource-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    logging.shutdown()
