from PIL import Image, ImageDraw, ImageFont


def composite(arena):
    canvas = Image.new("RGB", (960, 760), "#101824")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
        small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)
    except OSError:
        font = small = ImageFont.load_default()
    city = arena.config.scene == "cyber_city"
    draw.text(
        (22, 12),
        "NEON DISTRICT · G1 赛博街区" if city else "G1 视觉寻物与对抗 · 本地原型",
        font=font,
        fill="#e2ebf5",
    )
    draw.text(
        (670, 14),
        f"仿真时间 {arena.time:.1f} / {arena.config.duration:.0f} 秒",
        font=small,
        fill="#90a5ba",
    )
    for pid, p in enumerate(arena.referee.players):
        text = f"选手 {pid + 1}   任务分 {p.score:g}   生命 {p.health:g}"
        if p.respawn_at is not None:
            text += "   重生中"
        elif p.disabled_until > arena.time:
            text += "   暂时禁火"
        draw.text((22 + pid * 470, 49), text, font=font, fill="#7dd3fc" if pid == 0 else "#f9a8d4")
    canvas.paste(
        Image.fromarray(arena.overview(camera="city_hero" if city else "overview")).resize(
            (720, 480)
        ),
        (0, 90),
    )
    for pid in (0, 1):
        visual = arena._camera_frame(pid) if arena.cameras else None
        x, y = 722, 110 + pid * 225
        draw.text((x + 8, y - 20), f"选手 {pid + 1} · RGB 摄像头", font=small, fill="#cbd5e1")
        if visual:
            image = Image.fromarray(visual["rgb"]).resize((232, 174))
            canvas.paste(image, (x, y + 6))
    if city:
        from .city import VENUES, hiding_spots

        scene_text = f"双主街 / {len(VENUES)} 个可进入区域 / {len(hiding_spots())} 个候选藏点"
    else:
        scene_text = "任务：公共红杯 / 选手 1 蓝杯 / 选手 2 绿杯"
    draw.text((22, 585), scene_text, font=font, fill="#e2ebf5")
    draw.text(
        (22, 617),
        f"车辆撞击扣 {arena.config.traffic_damage:g} 生命；同车 {arena.config.traffic_contact_cooldown:g} 秒冷却。目标分布在室内，需自主搜索。"
        if city
        else "打错扣自身生命；对手被命中后扣血并暂时禁火；倒地 10 秒未起身则复位。",
        font=small,
        fill="#90a5ba",
    )
    events = [e for e in arena.referee.events if e["type"] not in ("invalid_action",)][-3:]
    for index, event in enumerate(events):
        detail = f"{event['time']:.2f}s  {event['type']}  player={event.get('player', '-')}"
        if "target" in event:
            detail += f"  {event['target']}  +{event['points']:g}"
        draw.text((22, 648 + index * 27), detail, font=small, fill="#a7bacd")
    return canvas


def save_gif(frames, path, seconds_per_frame=1):
    if frames:
        frames[0].save(
            path,
            save_all=True,
            append_images=frames[1:],
            duration=round(1000 * seconds_per_frame),
            loop=0,
        )
