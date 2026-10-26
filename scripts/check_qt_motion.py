"""Exercise interrupted motion, immediate actions and reduced-motion behavior.

Offscreen and disposable fixtures only; no desktop input or real game data.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
# Default browsing is asynchronous; all catalog data in this check is offline.
_catalog_stub = patch('launcher.catalog.search', return_value={'hits': [], 'total_hits': 0})


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.deps/qt')]
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtCore import QAbstractAnimation, QCoreApplication, QEvent, Qt, QRectF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from launcher.config import Config
from launcher.qtui.app import MainWindow
from launcher.qtui.motion import apply_motion_preferences
from launcher.qtui.widgets import ContentRow, ToggleSwitch, button, configure_fonts


def wait_for(predicate):
    deadline = time.monotonic() + 8
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate(), 'Motion or fixture task timed out'


def settled(window):
    wait_for(lambda:not window.nav_motion.running and not window.tasks.jobs)
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)


def assert_page_fixed(window):
    assert not hasattr(window,'motion'), 'Global page motion must stay removed'
    assert window.stack.currentWidget().pos().x()==0
    assert window.stack.currentWidget().pos().y()==0
    assert window.stack.currentWidget().graphicsEffect() is None


def almost_same(first,second):
    return all(abs(a-b)<.001 for a,b in zip(first.getRect(),second.getRect()))


_catalog_stub.start()
app = QApplication([])
app.setStyle('Fusion')
configure_fonts(app)
errors = []
def report_exception(kind, value, tb):
    errors.append(str(value))
    sys.__excepthook__(kind, value, tb)

sys.excepthook = report_exception

with tempfile.TemporaryDirectory(dir=ROOT / 'tmp', prefix='qt-motion-') as folder:
    root = Path(folder)
    config = Config(root / 'config/settings.json')
    config.set('game_dir', str(root / 'library'))
    version = root / 'library/versions/1.21.1'
    version.mkdir(parents=True)
    (version / '1.21.1.json').write_text(json.dumps({
        'id': '1.21.1', 'mainClass': 'Main', 'libraries': [],
    }), encoding='utf-8')
    window = MainWindow(config.path, root)
    window.show()
    wait_for(lambda: bool(window.versions) and not window.tasks.jobs)
    settled(window)

    window.navigate('download')
    settled(window)
    before_nav=dict(window.nav)
    browser=window.download_browser
    browser.query.setText('preserved query')
    browser.query.setFocus()
    scroll=browser.results.verticalScrollBar().value()
    window.navigate('download')
    assert window.download_browser is browser
    assert browser.query.text()=='preserved query'
    assert browser.results.verticalScrollBar().value()==scroll
    assert all(window.nav[key] is item for key,item in before_nav.items())
    assert not window.nav_motion.running
    assert_page_fixed(window)

    # A capsule stretches toward the new row; labels and live pages stay fixed.
    rail=window.nav_motion
    original_rect=QRectF(rail.rect)
    geometry={key:item.geometry() for key,item in window.nav.items()}
    window.choose_download_kind('resourcepack')
    assert all(window.nav[key] is item for key,item in before_nav.items())
    rail.animation.setCurrentTime(60)
    assert abs(rail.rect.top()-original_rect.top())<.001
    assert rail.rect.bottom()>original_rect.bottom()
    assert rail.rect.height()>original_rect.height()
    assert_page_fixed(window)
    before_input=window.stack.currentWidget().pos()
    QTest.keyClick(window.download_browser.query,Qt.Key.Key_A)
    assert window.stack.currentWidget().pos()==before_input
    assert rail.running, 'Input must not snap the capsule to its destination'
    rail.animation.setCurrentTime(175)
    assert original_rect.top()<rail.rect.top()<rail.destination.top()
    rail.animation.setCurrentTime(270)
    assert almost_same(rail.rect,rail.destination)
    assert all(window.nav[key].geometry()==rect for key,rect in geometry.items())

    # Rapid reversal resumes from the currently visible shape, not a saved endpoint.
    window.choose_download_kind('shader')
    rail.animation.setCurrentTime(90)
    middle=QRectF(rail.rect)
    window.choose_download_kind('mod')
    assert almost_same(rail.rect,middle)
    rail.animation.setCurrentTime(70)
    time_before=rail.animation.currentTime()
    window.navigate('download')
    assert rail.animation.currentTime()==time_before
    assert all(window.nav[key] is item for key,item in before_nav.items())
    settled(window)
    assert almost_same(rail.rect,rail.destination)

    # Real event-loop sampling observes intermediate shapes, without faking a frame rate.
    window.choose_download_kind('shader')
    samples=[]
    start=time.monotonic()
    while rail.running and time.monotonic()-start<2:
        app.processEvents()
        samples.append((round((time.monotonic()-start)*1000,2),list(rail.rect.getRect())))
        assert_page_fixed(window)
        QTest.qWait(8)
    assert not rail.running
    assert len({tuple(row[1]) for row in samples})>=5
    assert almost_same(rail.rect,rail.destination)
    (ROOT/'tmp/capsule-motion-samples.json').write_text(json.dumps(samples,indent=2))

    # Explicit refresh still rebuilds content; ordinary repeated navigation does not.
    window.navigate('versions')
    tree=window.version_tree
    nav=dict(window.nav)
    window.navigate('versions')
    assert window.version_tree is tree and all(window.nav[key] is value for key,value in nav.items())
    window.navigate('versions',force=True)
    assert window.version_tree is not tree
    window.resize(1180,780);QTest.qWait(15);assert_page_fixed(window)
    window.resize(1440,900);QTest.qWait(15)

    # A native click dispatches its action without waiting for press feedback.
    called = []
    control = button('Fixture action', lambda: called.append(True))
    control.setParent(window.stack.currentWidget())
    control.setGeometry(20, 20, 140, 40)
    control.show()
    QCoreApplication.sendEvent(control, QEvent(QEvent.Type.Enter))
    control.hover_animation.setCurrentTime(60)
    assert 0 < control.hover_amount < 1
    QTest.mousePress(control, Qt.MouseButton.LeftButton)
    control.press_animation.setCurrentTime(35)
    assert 0 < control.press_amount < 1
    QTest.mouseRelease(control, Qt.MouseButton.LeftButton)
    assert called == [True]
    control.setEnabled(False)
    assert control.hover_amount == control.press_amount == 0
    control.hide()

    # Result replacement is immediate; it never creates a faded screenshot layer.
    window.navigate('download')
    settled(window)
    browser = window.download_browser
    browser.query.setText('Fixture')
    hits = [{'project_id': 'fixture', 'title': 'Fixture', 'description': 'Mock result'}]
    with patch('launcher.catalog.search', return_value={'hits': hits, 'total_hits': 1}):
        browser.search()
        wait_for(lambda: not window.tasks.jobs)
    assert not hasattr(browser, 'results_motion')
    assert browser.results.graphicsEffect() is None
    assert len(browser.results.findChildren(ContentRow)) == 1
    obsolete=browser.results.findChildren(ContentRow)
    browser.empty()
    assert all(item.isHidden() for item in obsolete), 'Obsolete rows must not paint while awaiting deferred deletion'


    # Turning motion off finishes ongoing animation and applies to every control.
    window.choose_download_kind('resourcepack')
    assert rail.running
    window.config_obj.set('ui_animations', False)
    apply_motion_preferences(window)
    assert not rail.running
    window.navigate('settings')
    editor=window.settings_editor
    assert 'ui_animations' in editor.fields
    window.navigate('home')
    assert not rail.running
    nav = window.nav['versions']
    QCoreApplication.sendEvent(nav, QEvent(QEvent.Type.Enter))
    assert nav.hover_animation.state() == QAbstractAnimation.State.Stopped
    switch = ToggleSwitch()
    switch.setParent(window.stack.currentWidget())
    switch.show()
    switch.setChecked(True)
    assert switch.position == 1.0 and switch.motion.state() == QAbstractAnimation.State.Stopped
    window.config_obj.set('ui_animations', True)
    switch.setChecked(False)
    switch.motion.setCurrentTime(65)
    assert 0 < switch.position < 1
    switch.hide()
    window.navigate('settings')
    settled(window)
    window.open_settings_tab(editor.tab_names['外观'])
    assert rail.running
    window.hide()
    assert not rail.running
    window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

assert not errors, errors
print(json.dumps({
    'result': 'pass', 'fixture_only': True, 'desktop_input': False,
    'stable_content_geometry': True, 'reused_sidebar_controls': True, 'resize_and_hide_cleanup': True,
    'immediate_click_actions': True, 'no_result_opacity': True, 'no_page_animation': True, 'capsule_stretch_and_reversal': True,
    'reduced_motion': True, 'toggle_animation': True,
}))
