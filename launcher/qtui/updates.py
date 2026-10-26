"""Quiet startup checks and one compact, opt-in update prompt."""
import sys
from pathlib import Path
from PySide6.QtCore import QObject,QTimer,Qt,QRectF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication,QDialog,QMessageBox
from .widgets import column,row,label,button
from .tasks import TaskManager
from .theme import paint_color,corner
from .choices import ChoiceComboBox
from .. import updates


class UpdateDialog(QDialog):
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(paint_color(self,'base'))
        painter.drawRoundedRect(QRectF(self.rect()),corner(self,12),corner(self,12))


class UpdatePrompt(UpdateDialog):
    def __init__(self,owner,release):
        super().__init__(owner);self.setWindowTitle('启动器更新');self.setFixedWidth(460)
        title='发现新版本 ' if release.order>updates.LAUNCHER_UPDATE_ORDER else '切换到版本 '
        body=column(self,24,16);body.addWidget(label(title+release.version,'heading'))
        if release.notes:
            notes=label(release.notes,'muted',True)
            notes.setTextFormat(Qt.TextFormat.PlainText)
            notes.setMaximumHeight(180);body.addWidget(notes)
        body.addWidget(label('下载完成后将重启启动器，设置和游戏文件会保留。','muted',True))
        actions=row();actions.addStretch();later=button('稍后',self.reject);actions.addWidget(later)
        actions.addWidget(button('下载并重启',self.accept,'primary','download'));body.addLayout(actions)
        later.setDefault(True);later.setFocus()

class VersionPicker(UpdateDialog):
    def __init__(self,owner,releases):
        super().__init__(owner);self.setWindowTitle('版本管理');self.setFixedWidth(460)
        body=column(self,24,14);self.versions=ChoiceComboBox();self.versions.setAccessibleName('启动器版本')
        for item in releases:self.versions.addItem(item.version+('（当前）' if item.version==updates.LAUNCHER_VERSION else ''),item)
        body.addWidget(self.versions);self.notes=label('','muted',True);self.notes.setTextFormat(Qt.TextFormat.PlainText);self.notes.setMaximumHeight(180);body.addWidget(self.notes)
        self.warning=label('0.3.2 及以下版本不支持自动升级，之后需手动下载安装新版。','muted',True);body.addWidget(self.warning)
        body.addWidget(label('保留当前程序路径、文件名和设置。','muted',True))
        actions=row();actions.addStretch();actions.addWidget(button('取消',self.reject))
        self.proceed=button('安装并重启',self.accept,'primary','download');actions.addWidget(self.proceed);body.addLayout(actions)
        self.versions.currentIndexChanged.connect(self.changed);self.changed()

    def changed(self):
        item=self.versions.currentData()
        self.notes.setText(item.notes if item else '');self.warning.setVisible(bool(item and not item.supports_updater))
        self.proceed.setEnabled(bool(item and item.version!=updates.LAUNCHER_VERSION))

    def selected_release(self):return self.versions.currentData()


class UpdateController(QObject):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.checking=False;self.installing=False;self.pending=None;self.pending_manual=False;self.install_job_key=None;self.ready=None;self.timer=QTimer(self)
        self.timer.setSingleShot(True);self.timer.timeout.connect(self.offer)
        self.apply_timer=QTimer(self);self.apply_timer.setSingleShot(True);self.apply_timer.timeout.connect(self.apply)
        self.check_tasks=TaskManager(self)
        owner.tasks.bus.completed.connect(self.finished)

    def startup(self):
        if not updates.can_install():return
        if updates.finish_previous_updates(sys.executable):
            QMessageBox.warning(self.owner,'启动器更新未完成','上次自动更新未完成，请重试或从 GitHub 手动下载。原程序备份保存在 .onion/updates。')
        if self.owner.config_obj.get('check_launcher_updates'):self.check()

    def check(self,manual=False):
        if self.checking or self.installing:return
        self.checking=True;proxy=self.owner.repo.downloader.proxy
        def done(release):
            self.checking=False
            if release and (manual or self.owner.config_obj.get('check_launcher_updates')):
                self.pending=release;self.pending_manual=manual;self.offer()
            elif manual and not release:QMessageBox.information(self.owner,'检查更新','当前已是最新版本。')
        def failed(error):
            # Startup connectivity and malformed remote data never create UI.
            self.checking=False
        self.check_tasks.submit(lambda job:updates.check_update(proxy=proxy),done,failed)

    def manage_versions(self):
        if self.checking or self.installing:return
        self.checking=True;proxy=self.owner.repo.downloader.proxy
        def done(releases):
            self.checking=False;choices=updates.available_releases(releases)
            if not choices:return
            picker=VersionPicker(self.owner,choices)
            if picker.exec()==QDialog.DialogCode.Accepted and picker.proceed.isEnabled():self.install(picker.selected_release())
        def failed(error):self.checking=False
        self.check_tasks.submit(lambda job:updates.fetch_releases(proxy=proxy),done,failed)

    def busy(self):
        w=self.owner
        return bool(w.tasks.jobs or w.mutating or w.launch_pending or (w.process and w.process.proc.poll() is None)
            or QApplication.activeModalWidget() or not w.isVisible())

    def offer(self):
        if not self.pending or self.installing:return
        if not self.pending_manual and not self.owner.config_obj.get('check_launcher_updates'):
            self.pending=None;return
        if self.busy():self.timer.start(2000);return
        release=self.pending;self.pending=None
        if UpdatePrompt(self.owner,release).exec()==QDialog.DialogCode.Accepted:self.install(release)

    def install(self,release):
        if not updates.can_install():
            QMessageBox.information(self.owner,'启动器更新','源码运行时请更新源码；EXE 版支持自动替换。');return
        if self.busy():self.pending=release;self.pending_manual=True;self.timer.start(2000);return
        executable=Path(sys.executable).resolve();downloader=self.owner.repo.downloader;self.installing=True
        def work(job):return updates.download_update(release,executable,downloader,job)
        def done(staged):
            if job.cancel.is_set():self.installing=False;return
            self.ready=(executable,staged,release);self.apply()
        job=self.owner.task('更新启动器',work,done,mutates=True)
        if not job:self.installing=False
        else:self.install_job_key=job.key

    def finished(self,key,result,error):
        if key==self.install_job_key:
            self.install_job_key=None
            if error:self.installing=False

    def apply(self):
        if not self.ready:return
        if self.busy():self.apply_timer.start(500);return
        if not self.owner.flush_settings():self.installing=False;self.ready=None;return
        executable,staged,release=self.ready;self.ready=None
        try:
            from .window_size import remember_window_size
            remember_window_size(self.owner,self.owner.config_obj)
            updates.launch_replacement(executable,staged,release)
            self.owner.stop_offline_skin();QApplication.instance().quit()
        except (OSError,ValueError,RuntimeError) as error:self.installing=False;self.owner.error(error)
