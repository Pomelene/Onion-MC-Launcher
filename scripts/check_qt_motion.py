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

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.deps/qt')]
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtCore import QAbstractAnimation, QCoreApplication, QEvent, Qt
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
    wait_for(lambda: not window.motion.running and not window.tasks.jobs)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


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

    window.navigate('versions')
    assert window.current_page == 'versions'  # Route changes immediately.
    page = window.motion.page
    assert page is window.stack.currentWidget()
    positions = []
    for moment in (0, 30, 60, 90, 120, 160, 200, 240):
        window.motion.animation.setCurrentTime(moment)
        app.processEvents()
        positions.append(page.x())
    assert positions[0] == 18 and positions[-1] == 0, positions
    assert positions == sorted(positions, reverse=True), positions
    assert len(set(positions)) >= 5, positions
    assert page.graphicsEffect() is None
    settled(window)

    # Rapid transitions restore old page geometry and land on the final route.
    for route in ('settings', 'home', 'versions', 'download', 'home'):
        window.navigate(route)
    assert window.current_page == 'home'
    settled(window)
    assert all(window.stack.widget(i).x() == 0 for i in range(window.stack.count()))

    window.navigate('versions')
    assert window.motion.running
    QTest.keyClick(window.library_search, Qt.Key.Key_A)
    assert not window.motion.running  # Input reaches a live child immediately.

    window.navigate('home')
    settled(window)
    window.navigate('versions')
    window.resize(1180, 780)
    QTest.qWait(10)
    assert not window.motion.running
    window.resize(1440, 900)
    QTest.qWait(10)

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

    window.choose_download_kind('resourcepack')
    rail = window.nav_motion
    rail.animation.setCurrentTime(220)
    old_y = rail.y()
    window.choose_download_kind('shader')
    rail_positions = []
    for moment in (0, 40, 80, 120, 170, 220):
        rail.animation.setCurrentTime(moment)
        rail_positions.append(rail.y())
    assert rail_positions == sorted(rail_positions) and rail_positions[-1] > old_y, rail_positions
    assert len(set(rail_positions)) >= 4, rail_positions

    # Turning motion off finishes ongoing animation and applies to every control.
    window.navigate('settings')
    assert window.motion.running
    window.config_obj.set('ui_animations', False)
    apply_motion_preferences(window)
    assert not window.motion.running
    editor = window.settings_editor
    assert 'ui_animations' in editor.fields
    window.navigate('home')
    assert not window.motion.running
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
    window.navigate('versions')
    assert window.motion.running
    window.hide()
    assert not window.motion.running
    window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

assert not errors, errors
print(json.dumps({
    'result': 'pass', 'fixture_only': True, 'desktop_input': False,
    'interrupted_navigation': True, 'resize_and_hide_cleanup': True,
    'immediate_click_actions': True, 'no_result_opacity': True, 'monotonic_page_movement': True, 'sidebar_marker_movement': True,
    'reduced_motion': True, 'toggle_animation': True,
}))
