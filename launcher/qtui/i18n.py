"""Interface locale registry. Unknown strings fall back to their source text."""

_locale = 'zh-CN'
SUPPORTED = ('zh-CN', 'en-US')

EN = {
    '返回首页':'Home', '返回上一页':'Back', '账户':'Account', '添加账户':'Add account',
    '游戏':'Game', '实例管理':'Instance management', '实例列表':'Instances', '下载':'Download',
    '通用':'General', '工具坊':'Tools', '设置':'Settings', '关于':'About',
    '游戏设置':'Game settings', '自动安装':'Install components', '模组管理':'Mods',
    '资源包管理':'Resource packs', '光影管理':'Shaders', '世界管理':'Worlds',
    '原理图管理':'Schematics', '截图管理':'Screenshots', '运行日志':'Logs',
    '启动游戏':'Launch', '浏览实例目录':'Open instance folder', '管理':'Manage',
    '皮肤管理':'Skins', '种子地图':'Seed map', '新游戏':'New game', '安装游戏':'Install game',
    '整合包':'Modpacks', '游戏内容':'Game content', '模组':'Mods', '资源包':'Resource packs',
    '光影':'Shaders', '任务':'Tasks', '下载任务':'Download tasks', '任务中心':'Task center',
    '导入整合包':'Import modpack', '全局游戏设置':'Global game settings',
    '下载与网络':'Downloads and network', '启动器行为':'Launcher behavior', '外观':'Appearance',
    'Java 管理':'Java', '取消':'Cancel', '确定':'OK', '关闭':'Close', '保存':'Save',
    '安装':'Install', '搜索':'Search', '刷新':'Refresh', '选择版本':'Select version',
    '选择实例':'Select instance', '没有兼容版本':'No compatible versions',
    '语言':'Language', '重启启动器后生效':'Restart the launcher to apply',
}

EN.update({
    '界面外观':'Interface appearance', '显示模式':'Display mode', '跟随系统':'System', '深色':'Dark', '浅色':'Light',
    '粗体文字':'Bold text', '文字透明度':'Text transparency', 'UI 透明度':'UI transparency',
    '字体与可读性':'Fonts and readability', '界面字体':'Interface font', '界面字号':'Interface font size',
    '字体抗锯齿':'Font antialiasing', '日志字体':'Log font', '日志字号':'Log font size',
    '自动':'Automatic', '灰度':'Grayscale', '跟随界面字体':'Use interface font',
    '配色':'Colors', '颜色来源':'Color source', '自定义颜色':'Custom color', '跟随背景壁纸':'Match background',
    '色彩模式':'Color style', '保真':'Fidelity', '柔和点缀':'Soft accent', '鲜艳':'Vibrant', '中性':'Neutral',
    '水果沙拉':'Fruit salad', '彩虹':'Rainbow', '选择颜色':'Choose color', '颜色选择器':'Color picker',
    '当前主题色':'Current accent', '布局与动效':'Layout and animation', '标题栏透明':'Transparent title bar',
    '圆角大小':'Corner radius', '动画时长':'Animation duration', '界面动效':'Animations',
    '首页背景':'Home background', '背景范围':'Background coverage', '图片显示方式':'Image fit',
    '背景图片模糊':'Background blur', '背景透明度':'Background transparency', '自定义图片':'Custom image',
    '图片操作':'Image', '选择图片':'Choose image', '恢复默认':'Reset', '首页欢迎语':'Welcome message',
    '自定义主界面欢迎字样':'Custom welcome message', '大字':'Heading', '小字':'Subtitle',
    '恢复外观默认值':'Reset appearance', 'Java 运行环境':'Java runtime', 'Java 路径':'Java path',
    '内存分配':'Memory', '自动分配内存':'Allocate memory automatically', '最小内存':'Minimum memory',
    '最大内存':'Maximum memory', '自动分配参考':'Recommended allocation', '游戏窗口':'Game window',
    '窗口宽度':'Window width', '窗口高度':'Window height', '常用尺寸':'Window size presets', '全屏启动':'Fullscreen',
    '运行目录与快速加入':'Game directory and quick join', '游戏库目录':'Game folder', '版本隔离':'Instance isolation',
    '自动加入服务器':'Join server automatically', '下载设置':'Download settings', '下载源':'Download source',
    '并发下载数':'Concurrent downloads', '下载限速':'Download speed limit', '代理连接':'Proxy',
    '代理主机':'Proxy host', '代理端口':'Proxy port', '启动与退出':'Startup and exit',
    '启动后收起窗口':'Hide launcher after launch', '游戏退出后保留启动器':'Keep launcher open after game exits',
    '启动后显示日志页':'Show logs after launch', '启动器更新':'Launcher updates', '启动时检查更新':'Check for updates on startup',
    '当前版本':'Current version', '账号管理':'Accounts', '管理游戏账号':'Manage accounts', '高级参数':'Advanced',
    '启动参数':'Launch arguments', 'JVM 参数':'JVM arguments', '游戏参数':'Game arguments',
    '游戏进程优先级':'Game process priority', '启动前命令':'Pre-launch command', '游戏退出后命令':'Post-exit command',
    '试玩模式':'Demo mode', '默认':'Default', '较低':'Below normal', '较高':'Above normal',
})

CATALOGS = {'zh-CN': {}, 'en-US': EN}
from .i18n_en import EN as COMPLETE_EN
EN.update(COMPLETE_EN)

EN.update({
    '重命名':'Rename','复制实例':'Duplicate instance','重命名实例':'Rename instance','移除实例':'Remove instance',
    '实例名称':'Instance name','管理实例':'Manage instance','打开目录':'Open folder','打开所在目录':'Show in folder',
    '打开文件夹':'Open folder','添加游戏文件夹':'Add game folder','全部实例总览':'All instances',
    '导出整合包':'Export modpack','校验游戏文件':'Verify game files','启动前环境体检':'Pre-launch checks',
    '移入恢复区':'Move to recovery','移入恢复中心':'Move to recovery','恢复中心':'Recovery',
    '仅收藏':'Favorites only','全部标签':'All tags','名称排序':'Sort by name','全部类型':'All types',
    '全部实例':'All instances','原版':'Vanilla','收藏':'Favorite','取消收藏':'Remove favorite',
    '检查并更新':'Check for updates','已安装':'Installed','更换版本':'Change version',
    '稳定版':'Stable','正式版':'Release','测试版':'Beta','预览版':'Preview','刷新版本':'Refresh versions',
    '仅兼容版本':'Compatible versions only','更新日志':'Changelog','上一页':'Previous page','下一页':'Next page',
    '离线账号':'Offline account','微软正版登录':'Microsoft sign-in','需要重新登录':'Sign in again',
    '需要续期':'Session expired','移除账号':'Remove account','新建独立实例':'Create instance',
    '尚未选择游戏实例':'No instance selected','正在处理…':'Working…','正在获取版本…':'Loading versions…',
    '正在获取版本列表…':'Loading versions…','下载已取消':'Download cancelled','启动已取消':'Launch cancelled',
    '任务已取消':'Task cancelled','正在取消，请稍候…':'Cancelling…','尚未保存':'Unsaved changes',
    '最小化':'Minimize','最大化':'Maximize','还原':'Restore','不限速':'Unlimited','无披风':'No cape',
    '导出世界':'Export world','搜索选项':'Search options','操作未完成':'Operation failed',
    '取消任务':'Cancel task','重新尝试':'Retry','清除已结束记录':'Clear finished tasks',
    '任务':'Task','状态':'Status','进度 / 已接收':'Progress / received','时间':'Time',
    '已完成':'Completed','失败':'Failed','已取消':'Cancelled','下载中':'Downloading','等待中':'Queued',
    '游戏版本':'Game version','加载器':'Loader','发布时间':'Published','安装 Minecraft':'Install Minecraft',
    '安装选项':'Installation options','下载位置':'Download location','开始安装':'Install',
    '快照与旧版':'Snapshots and old versions','可用加载器版本':'Available loader versions',
    '搜索实例':'Search instances','添加模组':'Add mods','添加资源包':'Add resource pack',
    '添加世界':'Add world','下载世界':'Download worlds','显示全部':'Show all',
    '检查更新':'Check for updates','运行日志':'Game logs','复制':'Copy','删除':'Delete',
    '账户列表':'Accounts','添加认证服务器':'Add authentication server','离线模式':'Offline mode',
    '用户名':'Username','密码':'Password','登录':'Sign in','退出登录':'Sign out',
    '皮肤':'Skin','披风':'Cape','是否渲染披风':'Render cape','渲染披风':'Render cape',
    '导入皮肤':'Import skin','上传皮肤':'Upload skin','同步披风':'Sync capes',
    '选择披风':'Select cape','仅显示收藏':'Favorites only','查看源代码':'Source code','反馈':'Feedback',
})

def set_locale(locale):
    global _locale
    _locale = locale if locale in SUPPORTED else 'zh-CN'

def is_english():return _locale == 'en-US'
def get_locale():return _locale

def tr(text):
    return CATALOGS[_locale].get(text, text)


# Diagnostic templates are anchored. Captured names, paths and evidence are
# copied verbatim; no replacement is performed inside user-provided content.
MESSAGE_TEMPLATES = {
 '{0} 使用 {1}，当前为 {2}':'{0} uses {1}; current version is {2}',
 '{0} 声明与 {1} {2} 不兼容':'{0} is incompatible with {1} {2}',
 '{0} 要求 {1} {2}，当前 {3}':'{0} requires {1} {2}; current {3}',
 '{0} 包含条件或组合依赖，需由加载器进一步解析':'{0} has conditional dependencies requiring loader resolution',
 '该游戏要求 Java {0} 或更高，当前为 Java {1}':'This game requires Java {0} or newer; current Java is {1}',
 '启动时自动选择 Java {0}，未安装时下载对应运行时':'Select Java {0} on launch; download the runtime if needed',
 'OptiFine 安装完成：{0}':'OptiFine installed: {0}',
 '{0} 安装完成：{1}':'{0} installed: {1}',
 '下载 Java {0} 运行时（{1}）':'Downloading Java {0} runtime ({1})',
 '下载 OptiFine {0}':'Downloading OptiFine {0}',
 '下载 {0} 加载器配置':'Downloading {0} loader configuration',
 '下载 {0} 安装器 {1}':'Downloading {0} installer {1}',
 '安装 {0} 加载器':'Installing {0} loader','安装原版 {0}':'Installing vanilla {0}',
 '导入安装结果：{0}':'Importing installation: {0}','整合包导入完成：{0}':'Modpack imported: {0}',
 '整合包文件已就绪：{0}':'Modpack files ready: {0}',
 '查询 {0} 加载器版本':'Loading {0} loader versions','查询 {0} 版本列表':'Loading {0} versions',
 '获取 Java {0} 运行时清单':'Fetching Java {0} runtime manifest',
 '补全缺失依赖库 · {0} 个文件':'Downloading missing libraries · {0} files',
 '补全缺失或大小不符的资源 · {0} 个文件':'Repairing missing or incomplete assets · {0} files',
 '解析 CurseForge 文件（{0} 个）':'Resolving CurseForge files ({0})',
 '读取整合包：{0} {1}':'Reading modpack: {0} {1}',
 '跳过 {0} 个无法解析的可选文件':'Skipping {0} unresolved optional files',
 '运行 {0} 安装器（隔离安装）':'Running {0} installer (isolated)',
 '预下载安装器依赖（{0} 个，校验已有缓存）':'Preparing installer dependencies ({0}, checking cache)',
 '读取本地版本信息 · {0}':'Reading local version metadata · {0}',
 '获取 {0} 版本信息':'Fetching {0} version metadata',
}


def message(text):
    """Localize launcher-owned diagnostic messages, retaining opaque details."""
    if _locale != 'en-US' or not isinstance(text,str):return text
    if text in EN:return EN[text]
    import re
    for source,target in MESSAGE_TEMPLATES.items():
        parts=re.split(r'\{\d+\}',source)
        pattern='(.*?)'.join(re.escape(part) for part in parts)
        match=re.fullmatch(pattern,text,re.DOTALL)
        if match:return target.format(*match.groups())
    for source in sorted((key for key in EN if key.endswith(('：','： ','· '))),key=len,reverse=True):
        if text.startswith(source):return EN[source]+text[len(source):]
    return text
