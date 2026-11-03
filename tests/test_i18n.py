def test_locale_switch_and_fallback():
    from launcher.qtui.i18n import set_locale, tr
    try:
        set_locale('en-US')
        assert tr('设置') == 'Settings'
        assert tr('未收录的内容') == '未收录的内容'
        set_locale('zh-CN')
        assert tr('设置') == '设置'
        set_locale('unknown')
        assert tr('设置') == '设置'
    finally:
        set_locale('zh-CN')


def test_all_authored_qt_translation_keys_have_english():
    import ast,re
    from pathlib import Path
    from launcher.qtui.i18n import EN
    missing=[]
    for path in (Path(__file__).resolve().parents[1]/'launcher/qtui').glob('*.py'):
        if path.name in ('i18n.py','i18n_en.py'):continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='tr' and node.args and isinstance(node.args[0],ast.Constant):
                value=node.args[0].value
                if isinstance(value,str) and re.search('[\u4e00-\u9fff]',value) and value not in EN:missing.append((path.name,value))
    assert not missing,missing


def test_diagnostic_templates_preserve_paths_and_names():
    from launcher.qtui.i18n import message,set_locale
    try:
        set_locale('en-US')
        assert message('读取本地版本信息 · 我的实例')=='Reading local version metadata · 我的实例'
        assert message('该游戏要求 Java 25 或更高，当前为 Java 21')=='This game requires Java 25 or newer; current Java is 21'
        assert message('D:/下载/设置.jar')=='D:/下载/设置.jar'
        set_locale('zh-CN')
        assert message('检查客户端文件')=='检查客户端文件'
    finally:set_locale('zh-CN')
