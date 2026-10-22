"""Editable visual tokens and shared Qt surfaces for Onion's desktop UI.

Keep decoration quiet around dense game data. Accent is supplied by the user.
"""

BACKGROUND = '#14181d'
SURFACE = '#1c2229'
TEXT = '#edf2f4'
MUTED = '#a4b0ba'

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
QLineEdit:focus,QComboBox:focus,QPlainTextEdit:focus,QSpinBox:focus { border-color:#a58acb; }
QComboBox::drop-down { border:0; width:24px; }
QComboBox QAbstractItemView,QMenu { background:#252d35; color:#edf2f4; border:1px solid #43515a; selection-background-color:#493e59; }
QMenu::item { padding:9px 22px; }
QMenu::item:selected { background:#493e59; }
QTreeWidget { background:#1c2229; color:#edf2f4; border:1px solid #303941; border-radius:8px; padding:0; selection-background-color:#443852; }
QTreeWidget::item { padding:12px 9px; border-bottom:1px solid #303941; }
QTreeWidget::item:hover { background:#252f37; }
QTreeWidget::item:selected { background:#443852; color:#f3fcfb; }
QHeaderView::section { background:#222b33; border:0; border-bottom:1px solid #35404a; padding:10px; color:#aabac2; font-size:12px; }
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
QToolTip { background:#303c44; color:#f2f7f8; border:1px solid #50616a; padding:8px; }
QWidget#settingRow { background:transparent; border-bottom:1px solid #303941; }
QWidget#settingRow:hover { background:rgba(187,221,221,7); }
QWidget#settingRow QLineEdit,QWidget#settingRow QComboBox,QWidget#settingRow QSpinBox { background:transparent; border:1px solid transparent; padding:6px 8px; }
QWidget#settingRow QLineEdit:focus,QWidget#settingRow QSpinBox:focus { background:#342c40; border-color:#9a81bd; border-radius:5px; }
QSpinBox QLineEdit,QWidget#settingRow QSpinBox QLineEdit { padding:0; min-height:0; border:0; background:transparent; }
QWidget#listRow { background:#1c2229; border-bottom:1px solid #303941; }
QWidget#listRow:hover { background:#252f37; }
QDialog[embedded='true'] { background:transparent; }
'''
