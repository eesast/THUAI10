"""Developer-only walkability and visibility checks, never sent to policies."""

from collections import deque

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .city import (
    CITY_BOUNDS,
    CITY_LIMITS,
    CONNECTORS,
    SPAWNS,
    STREETS,
    VENUES,
    hiding_spots,
    world_position,
)


def _static(model, bid):
    while bid > 0:
        if model.body_mocapid[bid] >= 0 or model.body_jntnum[bid] > 0:
            return False
        bid = int(model.body_parentid[bid])
    return True


def static_obstacles(model, data):
    for gid in range(model.ngeom):
        if not model.geom_contype[gid] or not _static(model, int(model.geom_bodyid[gid])):
            continue
        kind = model.geom_type[gid]
        if kind == mujoco.mjtGeom.mjGEOM_PLANE:
            continue
        R = data.geom_xmat[gid].reshape(3, 3)
        size = model.geom_size[gid]
        if kind == mujoco.mjtGeom.mjGEOM_BOX:
            half = np.abs(R) @ size
        elif kind == mujoco.mjtGeom.mjGEOM_SPHERE:
            half = np.ones(3) * size[0]
        elif kind == mujoco.mjtGeom.mjGEOM_ELLIPSOID:
            half = np.sqrt((R * R) @ (size * size))
        elif kind in (mujoco.mjtGeom.mjGEOM_CYLINDER, mujoco.mjtGeom.mjGEOM_CAPSULE):
            half = np.abs(R[:, 2]) * size[1] + (
                np.ones(3) * size[0]
                if kind == mujoco.mjtGeom.mjGEOM_CAPSULE
                else np.sqrt(np.maximum(0, 1 - R[:, 2] ** 2)) * size[0]
            )
        else:
            continue
        center = data.geom_xpos[gid]
        yield gid, center, half


def navigation_grid(model, data, cell=0.12, radius=0.27):
    xmin, xmax, ymin, ymax = CITY_BOUNDS
    xs = np.arange(xmin, xmax, cell)
    ys = np.arange(ymin, ymax, cell)
    occupied = np.zeros((len(ys), len(xs)), dtype=bool)
    for gid, center, half in static_obstacles(model, data):
        if center[2] + half[2] < 0.06 or center[2] - half[2] > 1.45:
            continue
        xx = np.abs(xs - center[0]) <= half[0] + radius
        yy = np.abs(ys - center[1]) <= half[1] + radius
        occupied[np.ix_(yy, xx)] = True

    def index(point):
        return (int(round((point[1] - ymin) / cell)), int(round((point[0] - xmin) / cell)))

    start = index(SPAWNS[0])
    reached = np.zeros_like(occupied)
    queue = deque([start]) if not occupied[start] else deque()
    if not occupied[start]:
        reached[start] = True
    while queue:
        y, x = queue.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            yy, xx = y + dy, x + dx
            if (
                0 <= yy < len(ys)
                and 0 <= xx < len(xs)
                and not occupied[yy, xx]
                and not reached[yy, xx]
            ):
                reached[yy, xx] = True
                queue.append((yy, xx))
    return occupied, reached, index, (xmin, xmax, ymin, ymax), cell


def pedestrian_routes(model, data):
    from .city_actors import PEDESTRIANS

    obstacles = list(static_obstacles(model, data))
    report = {}
    for spec in PEDESTRIANS:
        half = np.array(
            [
                spec["radius"] + (0.20 if spec["kind"] == "robot" else 0.38),
                0.20 if spec["kind"] == "robot" else 0.18,
            ]
        )
        center = np.asarray(spec["center"])
        blocked = []
        for gid, point, size in obstacles:
            if point[2] + size[2] < 0.12 or point[2] - size[2] > 1.5:
                continue
            if np.all(np.abs(center - point[:2]) < half + size[:2]):
                blocked.append(model.geom(gid).name)
        report[spec["name"]] = {"clear": not blocked, "obstacles": blocked}
    return report


def validate_layout(model, data):
    occupied, reached, index, bounds, cell = navigation_grid(model, data)
    records = []
    for spot in hiding_spots():
        point = np.array(spot["position"])
        search = np.array(spot["search_position"], dtype=float)
        search[2] = 1.20
        direction = point - search
        distance = np.linalg.norm(direction)
        direction /= distance
        geom_id = np.array([-1], dtype=np.int32)
        hit = mujoco.mj_ray(
            model,
            data,
            search,
            direction,
            np.array([1, 0, 0, 1, 1, 1], dtype=np.uint8),
            1,
            -1,
            geom_id,
        )
        reachable = bool(reached[index(search)])
        visible = bool(hit < 0 or hit >= distance - 0.15)
        records.append(
            {
                "spot": spot["id"],
                "reachable": reachable,
                "visible_from_search_pose": visible,
                "blocking_geom": model.geom(int(geom_id[0])).name
                if not visible and geom_id[0] >= 0
                else None,
            }
        )
    entrances = {v["id"]: bool(reached[index(world_position(v, 0, 0.5))]) for v in VENUES}
    approaches = {
        v["id"]: all(
            not occupied[index(world_position(v, 0, depth))] for depth in np.linspace(-2.6, 0.3, 30)
        )
        for v in VENUES
    }
    streets = {s["id"]: bool(reached[index((0, s["y"], 0))]) for s in STREETS}
    connectors = {str(x): bool(reached[index((x, 15.0, 0))]) for x in CONNECTORS}
    return {
        "agent_radius_m": 0.27,
        "navigation_cell_m": cell,
        "venues": entrances,
        "entrance_approaches": approaches,
        "streets": streets,
        "connectors": connectors,
        "size_m": [CITY_LIMITS[1] - CITY_LIMITS[0], CITY_LIMITS[3] - CITY_LIMITS[2]],
        "spots": records,
        "reachable_spots": sum(r["reachable"] for r in records),
        "visible_spots": sum(r["visible_from_search_pose"] for r in records),
        "second_spawn_connected": bool(reached[index(SPAWNS[1])]),
        "spawn_clear": [bool(not occupied[index(p)]) for p in SPAWNS],
        "pedestrian_routes": pedestrian_routes(model, data),
    }


def draw_layout(model, data, path):
    occupied, reached, index, bounds, cell = navigation_grid(model, data)
    pixels = np.zeros((*occupied.shape, 3), dtype=np.uint8)
    pixels[:] = [21, 27, 49]
    pixels[reached] = [42, 55, 83]
    pixels[occupied] = [97, 87, 135]
    width = 1120
    height = round(width * (bounds[3] - bounds[2]) / (bounds[1] - bounds[0]))
    image = Image.fromarray(pixels[::-1]).resize((width, height), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
    except OSError:
        font = ImageFont.load_default()

    def point(p):
        y, x = index(p)
        return (round(x / occupied.shape[1] * width), round((1 - y / occupied.shape[0]) * height))

    for venue in VENUES:
        xy = point(world_position(venue, 0, venue["depth"] * 0.62))
        draw.text(
            xy,
            venue["title"].replace(" · ", "\n"),
            font=font,
            fill="#ecdcff",
            anchor="mm",
            align="center",
        )
    for street in STREETS:
        x, y = point((-1.0, street["y"], 0))
        draw.text((x, y - 17), street["title"], font=font, fill="#ffdc93", anchor="mm")
    for spot in hiding_spots():
        x, y = point(spot["position"])
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="#fda5ef")
        x, y = point(spot["search_position"])
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill="#6ef2e4")
    for i, spawn in enumerate(SPAWNS):
        x, y = point(spawn)
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill="#f4d37e")
        draw.text((x + 10, y), f"P{i + 1}", font=font, fill="white")
    draw.rectangle((0, 0, width, 43), fill="#0d1328")
    draw.text(
        (18, 8),
        "开发者地图 · 青点为搜索位置，粉点为藏点；此图不提供给选手",
        font=font,
        fill="#cfdbf2",
    )
    image.save(path)
