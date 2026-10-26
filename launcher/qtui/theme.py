"""Editable visual tokens and shared Qt surfaces for Onion's desktop UI.

Keep decoration quiet around dense game data. Accent is supplied by the user.
"""

from functools import lru_cache
from .opacity import opacity,alpha_byte,qss_color,parse_source_color

BACKGROUND = '#14181d'
SURFACE = '#1c2229'
TEXT = '#edf2f4'
MUTED = '#a4b0ba'

# Paint helpers and QSS share one appearance model; no widget-level fades.
PALETTES={
 'dark':{'base':'#14181d','surface':'#1c2229','text':'#edf2f4','muted':'#a4b0ba',
         'icon':'#bac7cd','selected_text':'#f0e8ff','disabled':'#687780',
         'track':'#3c4852','thumb':'#a4b0ba','check':'#253047','hover':'#eee3ff'},
 'light':{'base':'#f2f3f8','surface':'#ffffff','text':'#252536','muted':'#606577',
          'icon':'#626779','selected_text':'#493661','disabled':'#9a9eaa',
          'track':'#c8cbd5','thumb':'#ffffff','check':'#253047','hover':'#664285'},
}


def config_for(widget):
    while widget is not None:
        config=getattr(widget,'config_obj',None)
        if config is not None:return config
        launcher=getattr(widget,'launcher',None)
        if launcher is not None and hasattr(launcher,'config_obj'):return launcher.config_obj
        widget=widget.parentWidget()
    return {}


def appearance_values(config=None):
    config=config if config is not None else {}
    values={'color_mode':resolved_mode(config)}
    preview=getattr(config,'_qt_appearance_preview',{})
    values['bold_text']=bool(preview.get('bold_text',config.get('bold_text',False)))
    if values['color_mode'] not in PALETTES:values['color_mode']='dark'
    for key in ('text_transparency','ui_transparency','background_transparency'):
        try:value=int(preview.get(key,config.get(key,0)))
        except (TypeError,ValueError):value=0
        values[key]=max(0,min(70 if key=='text_transparency' else 90 if key=='ui_transparency' else 100,value))
    return values


# Every public appearance preference uses the same preview/save path.
APPEARANCE_KEYS={'accent_color','accent_source','color_style','color_mode','bold_text',
 'text_transparency','ui_transparency','background_image','background_mode','background_transparency',
 'background_scope','background_blur','titlebar_transparent','corner_radius','animation_duration',
 'font_family','font_size','log_font_family','log_font_size','font_antialiasing'}

def preference(config,key,default=None):
    return getattr(config,'_qt_appearance_preview',{}).get(key,config.get(key,default))

def system_color_mode():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    app=QGuiApplication.instance()
    return 'light' if app and app.styleHints().colorScheme()==Qt.ColorScheme.Light else 'dark'

def resolved_mode(config):
    mode=preference(config,'color_mode','dark')
    if mode=='auto':mode=system_color_mode()
    return mode if mode in PALETTES else 'dark'

def palette_for_config(config):
    from .color_science import palette
    from PySide6.QtGui import QColor
    seed=preference(config,'accent_color','#cebafa') or '#cebafa'
    if preference(config,'accent_source','custom')=='wallpaper':seed=getattr(config,'_qt_wallpaper_seed',seed)
    if not QColor(seed).isValid() or len(seed)!=7:seed='#cebafa'
    return palette(seed,resolved_mode(config),preference(config,'color_style','fidelity'))

def effective_accent(config):return palette_for_config(config)['accent']
def corner(widget,base=10):return max(0,min(24,int(preference(config_for(widget),'corner_radius',10))))*base/10
def text_size(widget,base=14):return round(base*int(preference(config_for(widget),'font_size',14))/14)
def row_height(widget,base=68):
    config=config_for(widget)
    return max(44,base+max(0,2*(int(preference(config,'font_size',14))-14)))


def surface_opacity(config=None):
    """Opacity of UI surfaces only; text and wallpaper have independent settings."""
    return opacity(preference(config or {},'ui_transparency',0),90)


def palette_for(widget):return palette_for_config(config_for(widget))


def paint_color(widget,role='text',text=False):
    from PySide6.QtGui import QColor
    color=QColor(palette_for(widget)[role])
    if text:color.setAlpha(alpha_byte(opacity(preference(config_for(widget),'text_transparency',0),70)))
    return color


def contrasting_accent(accent,mode):
    """Keep clickable foreground readable while retaining the chosen fill color."""
    from PySide6.QtGui import QColor
    color=QColor(accent);base=QColor(PALETTES[mode]['base'])
    def luminance(c):
        channels=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in c.getRgbF()[:3]]
        return sum(a*b for a,b in zip(channels,(.2126,.7152,.0722)))
    for _ in range(30):
        low,high=sorted((luminance(color),luminance(base)))
        if (high+.05)/(low+.05)>=4.5:break
        if mode=='light':color=color.darker(110)
        else:color=QColor.fromRgbF(*[v+(1-v)*.12 for v in color.getRgbF()[:3]])
    return color.name()


def _appearance_base(accent,config=None):
    import re
    values=appearance_values(config);mode=values['color_mode'];style=STYLE
    if mode=='light':
        colors={
         '#14181d':'#f2f3f8','#1c2229':'#ffffff','#edf2f4':'#252536',
         '#f3f8fa':'#252536','#bacbd0':'#606577','#a4b0ba':'#606577',
         '#687780':'#9a9eaa','#3e344c':'#ece5f7','#ddcafa':'#5b4379',
         '#303941':'#d9dce6','#2c343c':'#dadde7','#27242f':'#f3eef9',
         '#453e51':'#ded4ec','#dce5e9':'#343548','#303a43':'#e8e8f1',
         '#3a4851':'#dddded','#303d43':'#e1e2eb','#75858b':'#8b8e9c',
         '#ffacb2':'#b12f4c','#352d41':'#eee7f7','#252d35':'#f5f5fa',
         '#35404a':'#d7d9e4','#66557c':'#ded1f0','#43515a':'#d1d3df',
         '#493e59':'#e6dcf3','#443852':'#e9dff5','#252f37':'#f0edf6',
         '#f3fcfb':'#352447','#222b33':'#f4f3f8','#aabac2':'#616677',
         '#51616b':'#b3afc1','#8a9ba5':'#8b889c','#2a3239':'#e3e2eb',
         '#4b575f':'#bebdcb','#303c44':'#ffffff','#f2f7f8':'#252536',
         '#50616a':'#c4c1d2','#342c40':'#eee7f7',
        }
        style=re.sub(r'#[0-9a-fA-F]{6}',lambda match:colors.get(match.group().lower(),match.group()),style)
        style=style.replace('rgba(19,24,29,235)','rgba(249,249,253,235)').replace('rgba(19,24,29,245)','rgba(249,249,253,245)')
    tokens=palette_for_config(config or {});accent=tokens['accent']
    original=PALETTES[mode]
    replacement={original[role]:tokens[role] for role in ('base','surface','text','muted','icon','selected_text','disabled','track')}
    replacement.update({'#3e344c':tokens['container'],'#ece5f7':tokens['container'],
                        '#66557c':tokens['container'],'#443852':tokens['container'],
                        '#ddcafa':tokens['selected_text'],'#5b4379':tokens['selected_text']})
    style=re.sub(r'#[0-9a-fA-F]{6}',lambda match:replacement.get(match.group().lower(),match.group()),style)
    foreground=tokens['selected_text']
    style=style.replace('#cebafa',accent)
    style+='''
QWidget#settingRow QLineEdit,QWidget#settingRow QSpinBox,QWidget#settingRow QComboBox,QWidget#settingRow QPushButton { color:ACCENT; }
QWidget#settingRow QPushButton { text-align:right; }
QWidget#settingRow QPushButton:hover { background:rgba(155,125,195,20); }
QWidget#settingRow QLineEdit:disabled,QWidget#settingRow QSpinBox:disabled,QWidget#settingRow QComboBox:disabled,QWidget#settingRow QPushButton:disabled { color:DISABLED; }
QWidget#settingRow QLineEdit:read-only { color:MUTED; }
QPushButton[role='soft'] { color:ACCENT; }
QLabel#authCode { color:ACCENT; }
'''.replace('ACCENT',foreground).replace('DISABLED',tokens['disabled']).replace('MUTED',tokens['muted'])
    from PySide6.QtGui import QColor
    primary_text='#281f35' if QColor(accent).lightnessF()>.55 else '#ffffff'
    style+="\nQPushButton[role='primary'] { color:"+primary_text+"; }\n"
    from PySide6.QtGui import QColor
    tint=QColor(tokens['base'])
    backdrop='rgba(%d,%d,%d,150)'%tint.getRgb()[:3]
    style+='\nQWidget#sidebar[wallpaperUnderlay="true"],QWidget#toolbar[wallpaperUnderlay="true"] { background:'+backdrop+'; border:0; }\n'
    style+='\nQMainWindow { background:transparent; }\n'
    from PySide6.QtGui import QFontDatabase
    family=str(preference(config or {},'font_family','') or 'Microsoft YaHei UI')
    if family not in QFontDatabase.families():family='Microsoft YaHei UI'
    family=family.replace("'",'').replace('\\','')
    style=style.replace("font-family:'Microsoft YaHei UI'","font-family:'"+family+"'")
    size=int(preference(config or {},'font_size',14))
    style=re.sub(r'font-size:(\d+)px',lambda m:'font-size:'+str(round(int(m[1])*size/14))+'px',style)
    radius=int(preference(config or {},'corner_radius',10))
    style=re.sub(r'border-radius:(\d+)px',lambda m:'border-radius:'+str(round(int(m[1])*radius/10) if int(m[1])>=5 else int(m[1]))+'px',style)
    if values['bold_text']:style+='\nQWidget,QLabel#eyebrow,QLabel#muted { font-weight:600; }\n'
    return style


@lru_cache(maxsize=24)
def _cached_appearance_base(preferences):
    values=dict(preferences)
    return _appearance_base(values['accent_color'],values)


def appearance_style(accent,config=None):
    import re
    config=config if config is not None else {}
    seed=preference(config,'accent_color',accent)
    if preference(config,'accent_source','custom')=='wallpaper':seed=getattr(config,'_qt_wallpaper_seed',seed)
    # Alpha values deliberately do not participate in the expensive template cache.
    values={key:preference(config,key,default) for key,default in (
        ('color_style','fidelity'),('font_family',''),('font_size',14),('corner_radius',10),('bold_text',False))}
    values.update(color_mode=resolved_mode(config),accent_color=seed)
    style=_cached_appearance_base(tuple(sorted(values.items())))
    # Data surfaces use neutral chrome; the accent identifies focus and selection.
    dark=resolved_mode(config)=='dark';size=int(preference(config,'font_size',14))
    base,hover,selected,border,muted=('#121214','#1b1b1f','#25252b','#303034','#a1a1aa') if dark else ('#ffffff','#fafafa','#f0f0f3','#e5e5e7','#71717a')
    style+='''
QTreeWidget { background:transparent; border:0; border-radius:0; padding:0; outline:0; }
QTreeWidget::item,QTreeWidget::item:hover,QTreeWidget::item:selected { padding:0; border:0; background:transparent; }
QWidget#listRow { background:BASE; border:0; border-bottom:1px solid BORDER; border-radius:0; }
QWidget#listRow:hover { background:HOVER; }
QHeaderView::section { background:transparent; border:0; border-bottom:1px solid BORDER; padding:5px 12px; color:MUTED; font-size:HEADERpx; font-weight:400; }
QTreeWidget#instancePickerList { background:transparent; border:0; }
QTreeWidget#instancePickerList::item,QTreeWidget#instancePickerList::item:selected,QTreeWidget#instancePickerList::item:hover { padding:0; border:0; background:transparent; }
'''.replace('BASE',base).replace('HOVER',hover).replace('SELECTED',selected).replace('BORDER',border).replace('MUTED',muted).replace('HEADER',str(round(12*size/14)))
    text_opacity=opacity(preference(config,'text_transparency',0),70)
    if text_opacity<1:
        def text_alpha(match):
            rgb,_=parse_source_color(match[1]);return 'color:'+qss_color(rgb,text_opacity)
        style=re.sub(r'(?<![-\w])color:\s*(#[0-9a-fA-F]{6})',text_alpha,style)
    factor=surface_opacity(config)
    def fade_surface(match):
        def color_alpha(color_match):
            rgb,base_opacity=parse_source_color(color_match.group())
            return qss_color(rgb,base_opacity*factor)
        return match[1]+re.sub(r'#[0-9a-fA-F]{6}|rgba\([\d,]+\)',color_alpha,match[2])
    style=re.sub(r'((?<![-\w])(?:background(?:-color)?|selection-background-color|border(?:-(?:top|right|bottom|left))?(?:-color)?)\s*:\s*)([^;}]+)',fade_surface,style)
    if not preference(config,'titlebar_transparent',True):
        from PySide6.QtGui import QColor
        rgb=QColor(palette_for_config(config)['base']).getRgb()[:3]
        style+='\nQWidget#toolbar,QWidget#toolbar[wallpaperUnderlay="true"] { background:'+qss_color(rgb,1.)+'; border:0; }\n'
    return style


STYLE = '''
QMainWindow,QDialog { background:#14181d; }
QWidget { color:#edf2f4; font-family:'Microsoft YaHei UI'; font-size:14px; }
QWidget#windowResizeGrip { background:transparent; }
QPushButton#windowControl,QPushButton#windowClose { padding:0; border:0; border-radius:5px; }
QPushButton#windowClose:hover { background:#a63855; }
QPushButton#windowClose:pressed { background:#c34a68; }
QWidget#workspace { background:transparent; }
QWidget#sidebar { background:rgba(19,24,29,235); border-right:1px solid #2c343c; }
QWidget#toolbar { background:rgba(19,24,29,245); border-bottom:1px solid #2c343c; }
QLabel { background:transparent; }
QLabel#title { font-size:26px; font-weight:600; }
QLabel#heroTitle { font-size:44px; font-weight:600; color:#f3f8fa; }
QLabel#heroSubtitle { font-size:16px; color:#bacbd0; }
QLabel#heading { font-size:16px; font-weight:600; }
QLabel#muted { color:#a4b0ba; font-size:12px; }
QLabel#eyebrow { color:#a4b0ba; font-size:12px; font-weight:500; }
QLabel#settingTitle { color:#edf2f4; font-size:14px; }
QLabel:disabled,QLabel#settingTitle:disabled,QLabel#muted:disabled,QLabel#eyebrow:disabled { color:#687780; }
QLabel#pill { background:#3e344c; color:#ddcafa; padding:3px 7px; border-radius:4px; font-size:12px; }
QFrame#card,QWidget#settingsSection { background:#1c2229; border:1px solid #303941; border-radius:10px; }
QWidget#contextPanel { background:#27242f; border:1px solid #453e51; border-radius:8px; }
QWidget#contextPanel QComboBox { background:transparent; border:0; font-weight:600; }
QPushButton { background:transparent; border:1px solid transparent; border-radius:6px; padding:7px 12px; min-height:22px; color:#dce5e9; }
QPushButton:hover { background:#303a43; }
QPushButton:pressed { background:#3a4851; }
QPushButton[animated='true']:hover,QPushButton[animated='true']:pressed { background:transparent; }
QPushButton[animated='true'][role='primary']:hover,QPushButton[animated='true'][role='primary']:pressed { background:#cebafa; }
QPushButton:focus { border-color:#a58acb; }
QPushButton:disabled { color:#687780; background:transparent; }
QPushButton[role='primary'] { background:#cebafa; color:#281f35; font-weight:600; border:1px solid transparent; }
QPushButton[role='primary']:hover { background:#e0d1ff; }
QPushButton[role='primary']:disabled { background:#303d43; color:#75858b; }
QPushButton[role='soft'] { color:#cebafa; }
QPushButton[role='danger'] { color:#ffacb2; }
QPushButton[role='tab'] { border-radius:0; border-bottom:2px solid transparent; }
QPushButton[role='tab']:checked { border-bottom-color:#cebafa; background:#352d41; }
QLineEdit,QComboBox,QSpinBox,QPlainTextEdit,QListWidget { background:#252d35; color:#edf2f4; border:1px solid #35404a; border-radius:6px; padding:7px 10px; selection-background-color:#66557c; }
QLineEdit,QComboBox,QSpinBox { min-height:22px; }
QSlider::groove:horizontal { height:4px; border-radius:2px; background:#35404a; }
QSlider::sub-page:horizontal { background:#cebafa; border-radius:2px; }
QSlider::handle:horizontal { background:#cebafa; width:14px; margin:-5px 0; border-radius:7px; }
QSlider::handle:horizontal:hover { background:#e0d1ff; }
QLineEdit:focus,QComboBox:focus,QPlainTextEdit:focus,QSpinBox:focus { border-color:#a58acb; }
QComboBox::drop-down { border:0; width:24px; }
QComboBox QAbstractItemView,QMenu { background:#252d35; color:#edf2f4; border:1px solid #43515a; selection-background-color:#493e59; }
QMenu::item { padding:9px 22px; border-radius:6px; }
QMenu::item:selected { background:#493e59; }
QMenu::separator { height:1px; margin:5px 8px; background:#35404a; }
QScrollArea { border:0; background:transparent; }
QScrollArea>QWidget>QWidget { background:transparent; }
QScrollBar:vertical { background:transparent; width:7px; margin:2px; }
QScrollBar::handle:vertical { background:#51616b; border-radius:2px; min-height:30px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
QProgressBar { background:#303d43; border:0; border-radius:3px; height:6px; }
QProgressBar::chunk { background:#cebafa; border-radius:3px; }
QCheckBox { spacing:9px; padding:5px 0; min-height:20px; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid #8a9ba5; border-radius:4px; background:transparent; }
QCheckBox::indicator:checked { background:#cebafa; border-color:#cebafa; }
QCheckBox::indicator:disabled { background:#2a3239; border-color:#4b575f; }
QToolTip { background:#303c44; color:#f2f7f8; border:1px solid #50616a; border-radius:6px; padding:8px; }
QWidget#settingRow { background:transparent; border-bottom:1px solid #303941; }
QWidget#settingRow:hover { background:rgba(187,221,221,7); }
QWidget#settingRow QLineEdit,QWidget#settingRow QComboBox,QWidget#settingRow QSpinBox { background:transparent; border:1px solid transparent; padding:6px 8px; }
QWidget#settingRow QLineEdit:focus,QWidget#settingRow QSpinBox:focus { background:#342c40; border-color:#9a81bd; border-radius:5px; }
QSpinBox QLineEdit,QWidget#settingRow QSpinBox QLineEdit { padding:0; min-height:0; border:0; background:transparent; }
QDialog[embedded='true'] { background:transparent; }
QDialog#instancePicker,QTreeWidget#instancePickerList { background:transparent; border:0; }
QTreeWidget#instancePickerList::item,QTreeWidget#instancePickerList::item:selected,QTreeWidget#instancePickerList::item:hover { padding:0; border:0; background:transparent; }
QFrame#choicePopup,QListView#choiceList,QMenu { background:transparent; border:0; }
QMenu { padding:6px; }
QListView#choiceList { outline:0; padding:0; }
QListView#choiceList::item,QListView#choiceList::item:selected,QListView#choiceList::item:hover { background:transparent; border:0; padding:0; }
QLineEdit#choiceSearch { background:#252d35; border:1px solid #35404a; border-radius:7px; padding:7px 10px; }
'''
