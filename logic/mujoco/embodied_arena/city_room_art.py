"""Deterministic interior finishes and public street information panels."""

import numpy as np
from PIL import Image, ImageDraw

FINISHES = ("timber", "terrazzo", "marble", "carpet", "concrete", "ceramic")


def create_room_art(path, cjk, font):
    rng = np.random.default_rng(812)
    for kind in FINISHES:
        background = {
            "timber": "#765139",
            "terrazzo": "#c2b9a4",
            "marble": "#ccc5b4",
            "carpet": "#252b3d",
            "concrete": "#72787b",
            "ceramic": "#c4dcda",
        }[kind]
        im = Image.new("RGB", (512, 512), background)
        d = ImageDraw.Draw(im)
        if kind == "timber":
            for row in range(8):
                y = row * 64
                d.line((0, y, 512, y), fill="#3e3028", width=3)
                x = (row % 3) * 100 + 65
                d.line((x, y, x, y + 64), fill="#3e3028", width=2)
                for j in range(8):
                    yy = y + 6 + j * 7
                    d.line(
                        [(x, yy + 2 * np.sin(x * 0.025 + row)) for x in range(512)],
                        fill="#8b6747",
                        width=1,
                    )
        elif kind == "marble":
            for offset in (-150, -40, 130, 280, 450):
                line = [(x, offset + x * 0.62 + 8 * np.sin(x * 0.027)) for x in range(512)]
                d.line(line, fill="#b6ac97", width=3)
                d.line([(x, y + 3) for x, y in line], fill="#e2d9c6", width=2)
            d.rectangle((2, 2, 509, 509), outline="#8d7c60", width=3)
        elif kind in ("ceramic", "concrete"):
            for x in range(0, 512, 128):
                d.line((x, 0, x, 512), fill="#729b9d" if kind == "ceramic" else "#565d62", width=3)
                d.line((0, x, 512, x), fill="#729b9d" if kind == "ceramic" else "#565d62", width=3)
        else:
            for _ in range(3500):
                x, y = map(int, rng.integers(0, 512, 2))
                s = int(rng.integers(1, 4))
                color = (
                    ("#ad9b7e", "#ded5c0", "#7f837d")[int(rng.integers(3))]
                    if kind == "terrazzo"
                    else ("#30384b", "#1c2536")[int(rng.integers(2))]
                )
                d.rectangle((x, y, x + s, y + s), fill=color)
        im.save(path / f"city_floor_{kind}.png")
    for key, title, caption, color in (
        ("neon", "霓虹大道", "教堂 · 公园 · 商铺 · 充电区", "#7de9ef"),
        ("living", "烟火生活街", "饮品 · 小吃 · 酒店 · 邻里服务", "#ffda9c"),
    ):
        im = Image.new("RGB", (1024, 320), "#152337")
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((9, 9, 1015, 311), radius=20, outline=color, width=7)
        d.text((60, 35), title, font=cjk(105), fill=color)
        d.text((60, 215), caption, font=cjk(40), fill="#dce6ee")
        im.save(path / f"city_street_{key}.png")
    im = Image.new("RGB", (1024, 1024), "#152537")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((12, 12, 1012, 1012), radius=16, outline="#f0cb8b", width=7)
    d.text((55, 40), "街区导览", font=cjk(80), fill="#f4dfb8")
    rows = [
        (220, ["云栖酒店", "星际网吧", "糖葫芦", "便利店", "洗衣店"]),
        (445, ["蜜雪冰城", "瑞幸咖啡", "沙县小吃", "烤串", "五金店"]),
        (660, ["空港驿站", "流明教堂", "沙县小吃", "充电区", "绯红机厅"]),
        (875, ["蜜雪冰城", "以太公园", "瑞幸咖啡", "档案馆", "金灯夜市"]),
    ]
    for y, names in rows:
        for i, name in enumerate(names):
            x = 45 + i * 190
            d.rounded_rectangle((x, y, x + 174, y + 76), radius=7, fill="#314355")
            d.text((x + 9, y + 20), name, font=cjk(28), fill="#f2e4cd")
    for y, title in ((345, "烟火生活街"), (780, "霓虹大道")):
        d.rectangle((40, y - 23, 985, y + 23), fill="#92774f" if y == 345 else "#3b7287")
        d.text((430, y - 20), title, font=cjk(28), fill="white")
    for x in (210, 810):
        d.line((x, 380, x, 615), fill="#718896", width=14)
    d.text((55, 967), "文明通行  /  注意来车", font=cjk(26), fill="#b8d0d5")
    im.save(path / "city_directory.png")
    im = Image.new("RGB", (512, 512), "#234d47")
    d = ImageDraw.Draw(im)
    for x, y, symbol, color in (
        (110, 105, "A", "#a12939"),
        (285, 108, "K", "#162735"),
        (110, 292, "Q", "#162735"),
        (285, 290, "J", "#a12939"),
    ):
        d.rounded_rectangle(
            (x, y, x + 100, y + 130), radius=9, fill="#eee6d5", outline="#af9f83", width=3
        )
        d.text((x + 14, y + 14), symbol, font=font(35), fill=color)
        d.ellipse((x + 33, y + 70, x + 66, y + 104), fill=color)
    im.save(path / "city_leisure.png")
