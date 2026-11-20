"""Deterministic task appearances; references contain appearance but no world coordinates."""

import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw

SHAPES = ("cup", "bottle", "box", "ball", "can")
NAMES = {"cup": "杯子", "bottle": "饮料瓶", "box": "包裹盒", "ball": "球", "can": "罐子"}


def add_shape(body, identifier, shape, rgba):
    attrs = {"name": identifier + "/body", "rgba": rgba}
    if shape == "box":
        ET.SubElement(body, "geom", **attrs, type="box", size=".10 .09 .11")
    elif shape == "ball":
        ET.SubElement(body, "geom", **attrs, type="sphere", size=".11")
    elif shape == "bottle":
        ET.SubElement(body, "geom", **attrs, type="cylinder", size=".075 .105", pos="0 0 -.025")
        ET.SubElement(
            body,
            "geom",
            name=identifier + "/neck",
            type="cylinder",
            size=".035 .04",
            pos="0 0 .12",
            rgba=rgba,
        )
    else:
        ET.SubElement(body, "geom", **attrs, type="cylinder", size=".10 .13")
        if shape == "cup":
            for i, (a, b) in enumerate(
                [
                    ("0 .10 -.07", "0 .18 -.07"),
                    ("0 .18 -.07", "0 .18 .07"),
                    ("0 .18 .07", "0 .10 .07"),
                ]
            ):
                ET.SubElement(
                    body,
                    "geom",
                    name=f"{identifier}/handle{i}",
                    type="capsule",
                    fromto=a + " " + b,
                    size=".018",
                    rgba=rgba,
                )


def reference(shape, rgb):
    image = Image.new("RGB", (96, 96), (225, 225, 225))
    draw = ImageDraw.Draw(image)
    if shape == "box":
        draw.rectangle((22, 25, 73, 75), fill=rgb)
        draw.line((48, 25, 48, 75), fill=(80, 80, 80), width=3)
    elif shape == "ball":
        draw.ellipse((21, 21, 76, 76), fill=rgb)
    elif shape == "bottle":
        draw.rounded_rectangle((31, 31, 65, 78), radius=7, fill=rgb)
        draw.rectangle((40, 16, 56, 35), fill=rgb)
    else:
        draw.rectangle((26, 24, 69, 76), fill=rgb)
        draw.ellipse((26, 19, 69, 31), fill=rgb, outline=(80, 80, 80), width=2)
    return np.asarray(image).copy()


def distractors(world, config):
    from .city import hiding_spots
    from .scene import COLORS, _numbers, get_targets

    spots = hiding_spots()
    for index, target in enumerate(get_targets(config)):
        choices = [
            s for s in spots if s["zone"] == target["zone"] and s["position"] != target["position"]
        ]
        if not choices:
            continue
        point = choices[(config.seed + index) % len(choices)]["position"]
        identifier = "distractor/" + str(index)
        body = ET.SubElement(world, "body", name=identifier, pos=_numbers(point))
        shape = SHAPES[(SHAPES.index(target["shape"]) + 1) % len(SHAPES)]
        add_shape(body, identifier, shape, _numbers(COLORS[target["color"]]))
