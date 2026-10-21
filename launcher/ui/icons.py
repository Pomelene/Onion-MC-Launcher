"""统一的 24px 线性图标资源；按当前 DPI 超采样渲染，不依赖系统符号字体。"""
from functools import lru_cache
from PIL import Image, ImageDraw, ImageTk

# 每条折线均使用同一画布、笔画、端点和视觉尺寸。
PATHS = {
    "plus": [[(12, 5), (12, 19)], [(5, 12), (19, 12)]],
    "play": [[(8, 5), (19, 12), (8, 19), (8, 5)]],
    "download": [[(12, 3), (12, 15)], [(7, 10), (12, 15), (17, 10)], [(4, 16), (4, 21), (20, 21), (20, 16)]],
    "folder": [[(3, 7), (3, 20), (21, 20), (21, 7), (12, 7), (10, 4), (3, 4), (3, 7)]],
    "search": [[(15, 15), (21, 21)]],
    "account": [[(4, 21), (4, 18), (7, 15), (17, 15), (20, 18), (20, 21)]],
    "history": [[(3, 5), (3, 11), (9, 11)], [(12, 7), (12, 12), (16, 14)]],
    "restore": [[(3, 5), (3, 11), (9, 11)], [(9, 16), (12, 13), (15, 16)], [(12, 13), (12, 21)]],
    "package": [[(3, 7), (12, 3), (21, 7), (21, 17), (12, 21), (3, 17), (3, 7), (12, 11), (21, 7)], [(12, 11), (12, 21)], [(7, 5), (16, 9)]],
    "java": [[(5, 9), (5, 17), (8, 20), (15, 20), (18, 17), (18, 9), (5, 9)], [(18, 10), (22, 10), (22, 14), (18, 14)], [(9, 6), (10, 3)], [(14, 6), (15, 3)]],
    "settings": [[(3, 6), (21, 6)], [(3, 12), (21, 12)], [(3, 18), (21, 18)]],
    "arrow": [[(5, 12), (19, 12)], [(14, 7), (19, 12), (14, 17)]],
    "grid": [[(3, 3), (10, 3), (10, 10), (3, 10), (3, 3)], [(14, 3), (21, 3), (21, 10), (14, 10), (14, 3)], [(3, 14), (10, 14), (10, 21), (3, 21), (3, 14)], [(14, 14), (21, 14), (21, 21), (14, 21), (14, 14)]],
    "world": [[(3, 8), (9, 8), (11, 12), (9, 17), (12, 21)], [(14, 3), (14, 8), (20, 11)], [(16, 16), (21, 16)]],
}


@lru_cache(maxsize=256)
def raster(name, color, size):
    scale = 4
    image = Image.new("RGBA", (size * scale, size * scale))
    draw = ImageDraw.Draw(image)
    ratio = size * scale / 24
    stroke = max(1, round(ratio * 1.65))
    def points(items):
        return [(round(x * ratio), round(y * ratio)) for x, y in items]
    if name in ("search", "account", "world"):
        bounds = {"search": (3, 3, 17, 17), "account": (8, 3, 16, 11),
                  "world": (2, 2, 22, 22), "settings": (6, 6, 18, 18)}[name]
        draw.ellipse(tuple(round(v * ratio) for v in bounds), outline=color, width=stroke)
    if name == "settings":
        for x,y in ((8,6),(16,12),(10,18)):
            draw.ellipse(tuple(round(v*ratio) for v in (x-2,y-2,x+2,y+2)), fill=color)
    if name in ("history", "restore"):
        draw.arc(tuple(round(v * ratio) for v in (3, 3, 21, 21)), 195, 515, fill=color, width=stroke)
    for path in PATHS.get(name, PATHS["package"]):
        coords = points(path)
        if name == "play":
            draw.polygon(coords, fill=color)
        else:
            draw.line(coords, fill=color, width=stroke, joint="curve")
            r = stroke / 2
            for x, y in (coords[0], coords[-1]):
                draw.ellipse((x-r, y-r, x+r, y+r), fill=color)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def photo(master, name, color, size):
    return ImageTk.PhotoImage(raster(name, color, size), master=master)


def button_icon(text):
    for word, icon in (("启动", "play"), ("安装", "download"), ("导入", "package"),
                       ("新建", "plus"), ("Java", "java"), ("恢复", "restore"),
                       ("目录", "folder"), ("文件夹", "folder"), ("搜索", "search"),
                       ("设置", "settings"), ("模组", "package")):
        if word in text:
            return icon
    return None
