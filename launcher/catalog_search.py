"""Small, independently maintained search labels and common name aliases."""
import unicodedata

SORTS=(('相关度','relevance'),('热度','follows'),('下载量','downloads'),('最新发布','newest'),('最近更新','updated'))
CATEGORY_LABELS={
    'adventure':'冒险','cursed':'趣味','decoration':'装饰','economy':'经济','equipment':'装备',
    'food':'食物','game-mechanics':'游戏机制','library':'支持库','magic':'魔法','management':'管理',
    'minigame':'小游戏','mobs':'生物','optimization':'优化','social':'社交','storage':'存储',
    'technology':'科技','transportation':'交通','utility':'实用','worldgen':'世界生成',
    'challenging':'挑战','combat':'战斗','kitchen-sink':'综合','lightweight':'轻量','multiplayer':'多人',
    'quests':'任务','realistic':'写实','vanilla-like':'原版风格','simplistic':'简约','themed':'主题',
    'tweaks':'微调','gui':'界面','audio':'音效','fonts':'字体','blocks':'方块','entities':'实体',
    'items':'物品','models':'模型','environment':'环境','potato':'低配置','low':'低','medium':'中',
    'high':'高','screenshot':'截图','colored-lighting':'彩色光照','path-tracing':'路径追踪',
    'pbr':'PBR','shadows':'阴影','reflections':'反射','bloom':'泛光','atmosphere':'大气'}
# Names only; no third-party translation database is redistributed.
ALIASES={
    'mod':{'钠':'Sodium','锂':'Lithium','虹彩':'Iris Shaders','玉':'Jade','苹果皮':'AppleSkin',
           '模组菜单':'Mod Menu','地毯':'Carpet','迷你hud':'MiniHUD','投影':'Litematica',
           '物品管理器':'Just Enough Items','jei':'Just Enough Items','rei':'Roughly Enough Items',
           '粗略物品':'Roughly Enough Items','实体渲染机制优化':'Entity Culling',
           '动态fps':'Dynamic FPS','钠扩展':'Sodium Extra','鼠标手势':'Mouse Tweaks',
           '旅行地图':'JourneyMap','xaero的小地图':'Xaero Minimap','xaero的世界地图':'Xaero World Map',
           '机械动力':'Create','暮色森林':'Twilight Forest','农夫乐事':"Farmer's Delight",'连续纹理':'Continuity'},
    'shader':{'互补光影':'Complementary','互补':'Complementary','bsl光影':'BSL'},
    'resourcepack':{'新鲜动画':'Fresh Animations','鲜活动画':'Fresh Animations','原版高清':'Faithful'},
    'modpack':{'简单优化':'Simply Optimized','极致优化':'Fabulously Optimized'},
}

def search_terms(kind,query):
    text=' '.join(unicodedata.normalize('NFKC',str(query)).split())
    aliases=ALIASES.get(kind,{})
    return aliases.get(text.casefold()) or ' '.join(aliases.get(word.casefold(),word) for word in text.split())
