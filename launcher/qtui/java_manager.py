"""Embedded Java inventory with local scanning and inline download progress."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QTreeWidget,QTreeWidgetItem,QFileDialog,QProgressBar
from shiboken6 import isValid
from .widgets import column,row,label,button
from .choices import ChoiceComboBox


class JavaManager(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.loaded=False;self.scanning=False;self.job=None;self.on_selected=None
        body=column(self,0,12);top=row();top.addWidget(label('Java 运行时','heading'),1)
        self.refresh=button('重新检测',self.scan,glyph='refresh');top.addWidget(self.refresh)
        self.browse=button('手动添加',self.browse_java,glyph='folder');top.addWidget(self.browse);body.addLayout(top)
        self.current=label('','muted',True);body.addWidget(self.current)
        self.tree=QTreeWidget();self.tree.setRootIsDecorated(False);self.tree.setUniformRowHeights(True)
        self.tree.setHeaderLabels(['版本','架构','安装路径']);self.tree.setColumnWidth(0,150);self.tree.setColumnWidth(1,100)
        self.tree.setMinimumHeight(280);body.addWidget(self.tree,1)
        actions=row();self.major=ChoiceComboBox()
        for major in (8,17,21,25):self.major.addItem(f'Java {major}',major)
        self.major.setCurrentIndex(2);actions.addWidget(self.major)
        self.download=button('下载官方运行时',self.download_java,glyph='download');actions.addWidget(self.download)
        actions.addStretch();actions.addWidget(button('自动选择',lambda:self.apply('')))
        self.use=button('使用所选',self.choose,'primary');self.use.setEnabled(False);actions.addWidget(self.use);body.addLayout(actions)
        self.status=label('','muted',True);body.addWidget(self.status)
        progress=row();self.progress=QProgressBar();self.progress.setTextVisible(False);progress.addWidget(self.progress,1)
        self.cancel=button('取消下载',self.cancel_download);progress.addWidget(self.cancel);body.addLayout(progress)
        self.progress.hide();self.cancel.hide()
        self.tree.currentItemChanged.connect(lambda item,previous:self.use.setEnabled(bool(item) and self.job is None))
        self.tree.itemDoubleClicked.connect(lambda *_:self.choose());self.update_current()

    def showEvent(self,event):
        super().showEvent(event);self.update_current()
        if not self.loaded and not self.scanning:self.scan()

    def update_current(self):
        current=self.window.config_obj.get('java_path') or ''
        self.current.setText('当前：'+current if current else '当前：自动选择兼容的 Java')

    def add_info(self,info):
        if not info:return
        path=str(info.path)
        for i in range(self.tree.topLevelItemCount()):
            if self.tree.topLevelItem(i).data(0,Qt.ItemDataRole.UserRole)==path:return
        item=QTreeWidgetItem([f'Java {info.major} · {info.version}' if info.version else f'Java {info.major}',info.architecture or (f'{info.bits} 位' if info.bits else '—'),path])
        item.setData(0,Qt.ItemDataRole.UserRole,path);item.setToolTip(2,path);self.tree.addTopLevelItem(item)
        if path==self.window.config_obj.get('java_path'):self.tree.setCurrentItem(item)

    def scan(self):
        if self.scanning or self.job is not None:return
        self.scanning=True;self.refresh.setEnabled(False);self.download.setEnabled(False);self.status.setText('正在检测 Java…')
        from ..java import find_all_java,probe_java
        explicit=self.window.config_obj.get('java_path') or ''
        roots=[Path(entry['path'])/'runtime' for entry in self.window.game_libraries.entries()]
        if explicit:roots.append(Path(explicit).parent.parent)
        def work(job):
            infos=find_all_java(extra_roots=roots,refresh=True,cancel_event=job.cancel)
            if explicit and not any(str(info.path)==explicit for info in infos):
                info=probe_java(Path(explicit),refresh=True)
                if info:infos.insert(0,info)
            return infos
        def done(infos):
            if not isValid(self):return
            self.scanning=False;self.loaded=True;self.refresh.setEnabled(True);self.download.setEnabled(True);self.tree.clear()
            for info in infos:self.add_info(info)
            self.status.setText(f'找到 {len(infos)} 个运行时' if infos else '未检测到 Java，可手动添加或下载官方运行时')
        def failed(error):
            if isValid(self):self.scanning=False;self.refresh.setEnabled(True);self.download.setEnabled(True);self.status.setText('检测失败：'+str(error))
        self.window.tasks.submit(work,done,failed)

    def apply(self,path):
        if self.job is not None:return
        if self.on_selected:self.on_selected(path)
        else:
            editor=self.window.settings_editor;editor.java_chosen(path)
            if not editor.flush():self.status.setText('当前设置尚未保存，请等待任务完成');return
        if path:
            for i in range(self.tree.topLevelItemCount()):
                item=self.tree.topLevelItem(i)
                if item.data(0,Qt.ItemDataRole.UserRole)==path:self.tree.setCurrentItem(item);break
        else:self.tree.setCurrentItem(None);self.tree.clearSelection()
        self.update_current();self.status.setText('已使用所选 Java' if path else '已恢复自动选择 Java')

    def choose(self):
        item=self.tree.currentItem()
        if item:self.apply(item.data(0,Qt.ItemDataRole.UserRole))

    def browse_java(self):
        path,_=QFileDialog.getOpenFileName(self,'添加 Java','','Java (java.exe javaw.exe);;所有文件 (*)')
        if not path:return
        from ..java import probe_java
        def done(info):
            if not isValid(self):return
            if not info:self.status.setText('该文件不是可用的 Java 运行时');return
            self.add_info(info);self.status.setText('已添加到运行时列表，选择后点击“使用所选”')
        self.window.tasks.submit(lambda job:probe_java(Path(path),refresh=True),done,lambda error:self.status.setText(str(error)) if isValid(self) else None)

    def download_java(self):
        if self.scanning or self.job is not None or self.window.mutating or self.window.launch_pending:
            self.status.setText('请等待当前任务完成');return
        from ..java import download_java
        major=self.major.currentData();repo=self.window.repo;self.window.mutating=True
        self.download.setEnabled(False);self.refresh.setEnabled(False);self.use.setEnabled(False);self.progress.setRange(0,0);self.progress.show();self.cancel.show();self.cancel.setEnabled(True)
        def progress(value):
            if not isValid(self):return
            if isinstance(value,str):self.status.setText(value)
            elif isinstance(value,tuple):
                current,total=value
                if total>0:
                    self.progress.setRange(0,1000);self.progress.setValue(min(1000,int(current*1000/total)))
                    self.status.setText(f'下载 Java {major} · {current:,} / {total:,} · {current*100/total:.0f}%')
        def finish():
            cancelled=self.job.cancel.is_set();self.job=None;self.window.mutating=False
            if isValid(self):
                self.download.setEnabled(True);self.refresh.setEnabled(True);self.use.setEnabled(bool(self.tree.currentItem()));self.progress.hide();self.cancel.hide()
            return cancelled
        def done(info):
            cancelled=finish()
            if not isValid(self):return
            if cancelled:self.status.setText('下载已取消');return
            if info:self.add_info(info);self.apply(str(info.path))
            else:self.status.setText('该版本暂时没有可用的官方 Java 运行时')
        def failed(error):
            cancelled=finish()
            if isValid(self):self.status.setText('下载已取消' if cancelled else '下载失败：'+str(error))
        self.job=self.window.tasks.submit(lambda job:download_java(major,repo.downloader,job.emit,lambda a,b:job.emit((a,b))),done,failed,progress,repo.downloader)

    def cancel_download(self):
        if self.job:self.job.cancel.set();self.cancel.setEnabled(False);self.status.setText('正在取消下载…')
