"""Native scene textures: open-font signage and deterministic facade atlases."""

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import ROOT

ART = ROOT / "assets/cyber_city"
SIGNS = {
    "market": ("NOVA MARKET", "01 / OPEN EXCHANGE", "#65eaff"),
    "chapel": ("LUMEN CHAPEL", "02 / SANCTUARY", "#d6a5ff"),
    "charge": ("ION RECHARGE", "03 / ENERGY TERMINAL", "#72f5e5"),
    "park": ("AETHER PARK", "04 / BIOLUMINESCENCE", "#95f4d2"),
    "cafe": ("ORBIT CAFE", "05 / AFTER HOURS", "#ffa7e8"),
    "lab": ("SYNTH LAB", "06 / MEMORY ARCHIVE", "#a69cff"),
    "district": ("NEON / DISTRICT", "SECTOR 07   /   EMBODIED ARENA", "#94c9ff"),
    "transit": ("SKYLINE TRANSIT", "AUTONOMOUS / KEEP CLEAR", "#c0b4ff"),
    "station": ("SKYPORT TERMINAL", "07 / AIRLINK EXPRESS", "#fbd18a"),
    "tea": ("GOLDEN TEA", "08 / LATE NIGHT TEAHOUSE", "#f2d77a"),
    "noodle": ("MIDNIGHT RAMEN", "09 / NIGHT MARKET 24H", "#ffad66"),
    "arcade": ("CRIMSON ARCADE", "10 / PLAY AFTER DARK", "#ff6980"),
    "living": ("烟火生活街", "EVERYDAY / FOOD / REST / NEIGHBOURHOOD", "#ffdc93"),
}
ADVERTS = {
    "ramen": ("MIDNIGHT", "RAMEN / 24H", "#ffb76a", "#38121d", "bowl"),
    "tea": ("GOLDEN", "TEA / HAND BREWED", "#fbd682", "#16322e", "cup"),
    "music": ("AFTER HOURS", "LIVE / SECTOR 07", "#ff698a", "#211330", "wave"),
    "delivery": ("AIRLINK", "NEXT STOP / ANYWHERE", "#7fe9f3", "#102c3a", "flight"),
    "repair": ("FIX / REBOOT", "ROBOT CARE / 24H", "#ffd871", "#31221e", "gear"),
    "energy": ("ION ZERO", "CLEAN POWER / NEW LIFE", "#b5f99c", "#17312a", "bolt"),
    "fashion": ("NEON FORM", "FUTURE / EVERYDAY", "#d8a5ff", "#241836", "wave"),
    "night": ("NIGHT CITY", "STAY A LITTLE LONGER", "#ff9f78", "#321d30", "flight"),
}
SHOP_SIGNS = {
    "mixue": (
        "蜜雪冰城",
        "MIXUE / ICE CREAM & TEA",
        "#fff6e9",
        "#b71c32",
        ["冰鲜柠檬水", "珍珠奶茶", "甜筒冰淇淋"],
    ),
    "luckin": (
        "瑞幸咖啡",
        "LUCKIN COFFEE / PICK UP",
        "#ffffff",
        "#173a79",
        ["生椰拿铁", "美式咖啡", "外带取餐"],
    ),
    "shaxian": (
        "沙县小吃",
        "SHAXIAN / LOCAL KITCHEN",
        "#ffe3a0",
        "#8e2721",
        ["拌面 · 扁肉", "蒸饺 · 炖罐", "现做堂食"],
    ),
    "skewers": (
        "老街烤串",
        "CHARCOAL BBQ / LATE NIGHT",
        "#ffcd75",
        "#512c27",
        ["羊肉串 · 鸡翅", "炭火烧烤", "夜宵营业"],
    ),
    "hardware": (
        "邻里五金店",
        "HARDWARE / TOOLS & REPAIR",
        "#e2e7bd",
        "#304940",
        ["螺丝 · 工具", "电线 · 水管", "修理配件"],
    ),
    "hotel": (
        "云栖酒店",
        "CLOUD REST HOTEL / 24H",
        "#ffe0a0",
        "#4e363b",
        ["24H 酒店前台", "客房 · 休息", "行李寄存"],
    ),
    "netcafe": (
        "星际网吧",
        "ORBIT ESPORTS / INTERNET",
        "#bcf5ff",
        "#252d57",
        ["电竞开黑", "高速网络", "饮料零食"],
    ),
    "tanghulu": (
        "巷口糖葫芦",
        "TANGHULU / HANDMADE SWEETS",
        "#fff0d0",
        "#9f3130",
        ["山楂 · 草莓", "现熬糖衣", "手作串串"],
    ),
    "convenience": (
        "便利蜂巢",
        "24H / EVERYDAY STORE",
        "#f6ffde",
        "#426745",
        ["饮料 · 零食", "日用品 · 补给", "24小时营业"],
    ),
    "laundry": (
        "净界自助洗衣",
        "LAUNDRY / WASH & DRY",
        "#e5ffff",
        "#286a7a",
        ["洗衣 · 烘干", "自助投放", "等候休息"],
    ),
}
SIGNS.update({k: (v[0], v[1], v[2]) for k, v in SHOP_SIGNS.items()})


def ensure_art():
    font_path = ROOT / "third_party/orbitron/Orbitron.ttf"
    fingerprint = hashlib.sha256(
        font_path.read_bytes() if font_path.exists() else b"fallback"
    ).hexdigest()[:16]
    stamp = ART / "version.json"
    cjk_path = next(
        (
            Path(p)
            for p in (
                "C:/Windows/Fonts/msyhbd.ttc",
                "C:/Windows/Fonts/msyh.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                "/System/Library/Fonts/PingFang.ttc",
            )
            if Path(p).exists()
        ),
        None,
    )
    version = {"generator": 11, "font": fingerprint, "cjk": str(cjk_path)}
    required = (
        [ART / f"city_sign_{k}.png" for k in SIGNS]
        + [ART / f"city_ad_{k}.png" for k in ADVERTS]
        + [ART / f"city_facade_{i}.png" for i in range(6)]
        + [ART / f"city_menu_{k}.png" for k in SHOP_SIGNS]
        + [ART / "city_living_paving.png", ART / "city_desktop.png"]
    )
    from .city_room_art import FINISHES, create_room_art

    required += [ART / f"city_floor_{k}.png" for k in FINISHES] + [
        ART / f"city_{k}.png" for k in ("street_neon", "street_living", "directory", "leisure")
    ]
    if (
        stamp.exists()
        and json.loads(stamp.read_text()) == version
        and all(p.exists() for p in required)
    ):
        return
    ART.mkdir(parents=True, exist_ok=True)

    def font(size):
        try:
            return ImageFont.truetype(str(font_path), size)
        except OSError:
            return ImageFont.truetype("DejaVuSans.ttf", size)

    def cjk(size):
        return ImageFont.truetype(str(cjk_path), size) if cjk_path else font(size)

    for key, (title, subtitle, color) in SIGNS.items():
        if key in SHOP_SIGNS:
            continue
        image = Image.new("RGB", (1024, 256), "#090e25")
        draw = ImageDraw.Draw(image)
        for y in range(0, 256, 8):
            draw.line((0, y, 1024, y), fill="#111a37")
        draw.rounded_rectangle((6, 6, 1017, 249), radius=14, outline=color, width=5)
        draw.rectangle((24, 22, 34, 234), fill=color)
        draw.line((50, 194, 974, 194), fill=color, width=2)
        text_font = font(64) if title.isascii() else cjk(76)
        while draw.textbbox((0, 0), title, font=text_font)[2] > 880:
            text_font = font(text_font.size - 2)
        box = draw.textbbox((0, 0), title, font=text_font)
        draw.text(
            ((1024 - (box[2] - box[0])) / 2, 62), title, font=text_font, fill=color, stroke_width=1
        )
        draw.text((62, 208), subtitle, font=font(20), fill="#b9c8e8")
        for x in range(860, 974, 20):
            draw.rectangle((x, 27, x + 8, 42), fill=color)
        image.save(ART / f"city_sign_{key}.png")

    def cjk(size):
        return ImageFont.truetype(str(cjk_path), size) if cjk_path else font(size)

    for key, (title, subtitle, ink, background, items) in SHOP_SIGNS.items():
        image = Image.new("RGB", (1024, 256), background)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((9, 9, 1015, 247), radius=8, outline=ink, width=4)
        face = cjk(111)
        box = draw.textbbox((0, 0), title, font=face)
        draw.text(((1024 - box[2]) / 2, 22), title, font=face, fill=ink)
        draw.line((55, 185, 969, 185), fill=ink, width=2)
        draw.text((58, 208), subtitle, font=font(20), fill=ink)
        image.save(ART / f"city_sign_{key}.png")
        image = Image.new("RGB", (512, 768), background)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((12, 12, 500, 756), radius=12, outline=ink, width=5)
        draw.text((38, 55), title, font=cjk(66), fill=ink)
        for i, item in enumerate(items):
            draw.text((38, 270 + i * 111), item, font=cjk(46), fill=ink)
            draw.line((38, 338 + i * 111, 474, 338 + i * 111), fill=ink, width=2)
        draw.text((40, 670), "OPEN / WELCOME", font=font(25), fill=ink)
        image.save(ART / f"city_menu_{key}.png")
    for key, (title, subtitle, accent, background, icon) in ADVERTS.items():
        image = Image.new("RGB", (768, 1024), background)
        draw = ImageDraw.Draw(image)
        for y in range(0, 1024, 12):
            draw.line((0, y, 768, y), fill="#172030", width=1)
        draw.rectangle((15, 15, 752, 1008), outline=accent, width=7)
        draw.rectangle((38, 44, 730, 52), fill=accent)
        title_font = font(64)
        while draw.textbbox((0, 0), title, font=title_font)[2] > 660:
            title_font = font(title_font.size - 2)
        draw.text((54, 90), title, font=title_font, fill=accent)
        draw.text((55, 185), subtitle, font=font(22), fill="#f4e9da")
        draw.text((55, 938), "NEON DISTRICT / EST. 2089", font=font(19), fill=accent)
        if icon in ("bowl", "cup"):
            if icon == "bowl":
                draw.pieslice((155, 405, 615, 740), 0, 180, fill=accent)
                draw.ellipse((155, 400, 615, 465), fill=background, outline=accent, width=10)
                draw.line((270, 415, 580, 285), fill="#fff0d5", width=13)
                draw.line((290, 445, 610, 315), fill="#fff0d5", width=13)
                draw.rectangle((295, 720, 475, 745), fill=accent)
            else:
                draw.rounded_rectangle((220, 400, 500, 700), radius=30, outline=accent, width=14)
                draw.arc((440, 435, 600, 625), 270, 90, fill=accent, width=15)
                draw.ellipse((215, 385, 505, 455), fill=background, outline=accent, width=11)
                draw.line((175, 740, 575, 740), fill=accent, width=10)
            for offset in (-100, 0, 100):
                points = [(384 + offset + 22 * np.sin(t * 0.15), 350 - t * 4) for t in range(35)]
                draw.line(points, fill=accent, width=5)
        elif icon == "wave":
            for row in range(6):
                points = [
                    (90 + x, 475 + row * 38 + 55 * np.sin(x * 0.019 + row * 0.65))
                    for x in range(590)
                ]
                draw.line(points, fill=accent, width=7)
            draw.ellipse((280, 350, 488, 558), outline="#ffe0da", width=8)
        elif icon == "flight":
            draw.polygon([(130, 620), (615, 340), (462, 725), (377, 572)], outline=accent, width=14)
            draw.line((377, 572, 615, 340), fill=accent, width=8)
            for j in range(4):
                draw.line((130, 720 + j * 35, 330 - j * 20, 720 + j * 35), fill=accent, width=5)
        elif icon == "bolt":
            draw.polygon(
                [(405, 310), (220, 575), (350, 575), (290, 800), (560, 465), (410, 465)],
                fill=accent,
            )
        else:
            draw.ellipse((205, 390, 565, 750), outline=accent, width=30)
            draw.ellipse((300, 485, 470, 655), outline=accent, width=14)
            for a in np.linspace(0, 2 * np.pi, 12, endpoint=False):
                draw.line(
                    (
                        385 + 170 * np.cos(a),
                        570 + 170 * np.sin(a),
                        385 + 210 * np.cos(a),
                        570 + 210 * np.sin(a),
                    ),
                    fill=accent,
                    width=27,
                )
        for x in range(560, 715, 18):
            draw.rectangle((x, 835, x + 6, 885), fill=accent)
        draw.text((55, 835), "OPEN / 24 : 00", font=font(25), fill="#f4e9da")
        image.save(ART / f"city_ad_{key}.png")
    rng = np.random.default_rng(71)
    for index, color in enumerate(
        (
            (58, 117, 169),
            (100, 75, 175),
            (51, 144, 158),
            (212, 144, 65),
            (186, 68, 62),
            (139, 164, 153),
        )
    ):
        image = Image.new("RGB", (256, 512), (13, 18, 35))
        draw = ImageDraw.Draw(image)
        for row in range(32):
            for col in range(8):
                lit = rng.random() > 0.32
                level = rng.uniform(0.35, 1.0) if lit else 0.09
                fill = tuple(round(c * level) for c in color)
                draw.rectangle(
                    (col * 32 + 7, row * 16 + 4, col * 32 + 23, row * 16 + 10), fill=fill
                )
        draw.line((0, 0, 0, 512), fill=(40, 70, 100), width=3)
        image.save(ART / f"city_facade_{index}.png")
    image = Image.new("RGB", (512, 512), (37, 43, 64))
    draw = ImageDraw.Draw(image)
    for x in range(0, 512, 128):
        draw.line((x, 0, x, 512), fill=(69, 78, 102), width=3)
        draw.line((0, x, 512, x), fill=(69, 78, 102), width=3)
    for _ in range(1800):
        x, y = rng.integers(0, 512, 2)
        draw.point((int(x), int(y)), fill=(43, 50, 73))
    image.save(ART / "city_paving.png")
    image = Image.new("RGB", (512, 512), (105, 87, 76))
    draw = ImageDraw.Draw(image)
    for row in range(8):
        for col in range(5):
            x = col * 128 - (64 if row % 2 else 0)
            draw.rectangle(
                (x, row * 64, x + 124, row * 64 + 60),
                fill=(111 + row % 3 * 4, 94 + col % 2 * 4, 82),
                outline=(148, 125, 99),
                width=2,
            )
    image.save(ART / "city_living_paving.png")
    image = Image.new("RGB", (512, 320), "#10243c")
    draw = ImageDraw.Draw(image)
    draw.text((20, 18), "ORBIT / ONLINE", font=font(24), fill="#95ebff")
    draw.rounded_rectangle((25, 65, 350, 285), radius=8, fill="#173750", outline="#5fc3d2", width=3)
    draw.ellipse((90, 85, 280, 275), outline="#ad7dfb", width=4)
    draw.line((95, 180, 280, 180), fill="#97f5ec", width=2)
    draw.line((188, 90, 188, 275), fill="#97f5ec", width=2)
    for row in range(7):
        draw.rectangle(
            (375, 70 + row * 29, 485, 81 + row * 29), fill="#497481" if row % 2 else "#ad7dfb"
        )
    image.save(ART / "city_desktop.png")
    create_room_art(ART, cjk, font)
    stamp.write_text(json.dumps(version), encoding="utf-8")
