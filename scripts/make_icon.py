# -*- coding: utf-8 -*-
"""生成启动器图标（assets/craftbridge.ico）。

用 Pillow 画一个等距方块：深色圆角底 + 三面蓝绿渐变，无外部素材依赖。
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "craftbridge.ico"
SIZE = 256


def rounded_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def main() -> None:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # 背景：深色圆角方块 + 顶部微亮
    rounded_rect(draw, (8, 8, SIZE - 8, SIZE - 8), 52, (17, 24, 39, 255))
    rounded_rect(draw, (8, 8, SIZE - 8, 96), 52, (31, 41, 55, 255))

    # 等距方块三个面：顶面菱形 + 左右两个侧面
    cx, cy = SIZE // 2, SIZE // 2
    half_w, half_h, depth = 76, 42, 56
    top = [(cx, cy - depth - half_h), (cx + half_w, cy - depth),
           (cx, cy + half_h - depth), (cx - half_w, cy - depth)]
    left = [(cx - half_w, cy - depth), (cx, cy + half_h - depth),
            (cx, cy + half_h), (cx - half_w, cy)]
    right = [(cx + half_w, cy - depth), (cx, cy + half_h - depth),
             (cx, cy + half_h), (cx + half_w, cy)]

    draw.polygon(top, fill=(96, 165, 250, 255))
    draw.polygon(left, fill=(37, 99, 235, 255))
    draw.polygon(right, fill=(29, 78, 216, 255))

    # 顶面高光与方块纹路
    draw.line([(cx - half_w + 6, cy - depth + 4), (cx, cy - depth + half_h - 2)],
              fill=(147, 197, 253, 255), width=6)
    draw.line([(cx, cy - depth + half_h - 2), (cx, cy + half_h + 12)],
              fill=(30, 64, 175, 255), width=4)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                           (128, 128), (256, 256)])
    print("icon written:", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()