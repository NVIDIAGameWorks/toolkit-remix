"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

from __future__ import annotations

__all__ = ["earclip_polygon_with_holes", "earcut", "triangulate_shapely_polygon"]

import math

import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

_EPSILON = 1e-12
# Below this vertex count the z-order hash of earcut costs more than it saves.
_HASH_THRESHOLD = 80
_Z_RANGE = 32767


class _Node:
    """Vertex of the circular doubly linked ring earcut works on."""

    __slots__ = ("i", "x", "y", "prev", "next", "z", "prev_z", "next_z", "steiner")

    def __init__(self, index: int, x: float, y: float):
        self.i = index
        self.x = x
        self.y = y
        self.prev: _Node | None = None
        self.next: _Node | None = None
        self.z = 0
        self.prev_z: _Node | None = None
        self.next_z: _Node | None = None
        self.steiner = False


def _area(p: _Node, q: _Node, r: _Node) -> float:
    return (q.y - p.y) * (r.x - q.x) - (q.x - p.x) * (r.y - q.y)


def _equals(p: _Node, q: _Node) -> bool:
    return p.x == q.x and p.y == q.y


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _on_segment(p: _Node, q: _Node, r: _Node) -> bool:
    return min(p.x, r.x) <= q.x <= max(p.x, r.x) and min(p.y, r.y) <= q.y <= max(p.y, r.y)


def _intersects(p1: _Node, q1: _Node, p2: _Node, q2: _Node) -> bool:
    o1 = _sign(_area(p1, q1, p2))
    o2 = _sign(_area(p1, q1, q2))
    o3 = _sign(_area(p2, q2, p1))
    o4 = _sign(_area(p2, q2, q1))
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _on_segment(p1, p2, q1):
        return True
    if o2 == 0 and _on_segment(p1, q2, q1):
        return True
    if o3 == 0 and _on_segment(p2, p1, q2):
        return True
    return o4 == 0 and _on_segment(p2, q1, q2)


def _point_in_triangle(ax, ay, bx, by, cx, cy, px, py) -> bool:
    return (
        (cx - px) * (ay - py) >= (ax - px) * (cy - py)
        and (ax - px) * (by - py) >= (bx - px) * (ay - py)
        and (bx - px) * (cy - py) >= (cx - px) * (by - py)
    )


def _insert_node(index: int, x: float, y: float, last: _Node | None) -> _Node:
    node = _Node(index, x, y)
    if last is None:
        node.prev = node
        node.next = node
    else:
        node.next = last.next
        node.prev = last
        last.next.prev = node
        last.next = node
    return node


def _remove_node(node: _Node) -> None:
    node.next.prev = node.prev
    node.prev.next = node.next
    if node.prev_z is not None:
        node.prev_z.next_z = node.next_z
    if node.next_z is not None:
        node.next_z.prev_z = node.prev_z


def _signed_area_flat(data: list[float], start: int, end: int) -> float:
    total = 0.0
    j = end - 2
    for i in range(start, end, 2):
        total += (data[j] - data[i]) * (data[i + 1] + data[j + 1])
        j = i
    return total


def _linked_list(data: list[float], start: int, end: int, clockwise: bool) -> _Node | None:
    last = None
    if clockwise == (_signed_area_flat(data, start, end) > 0):
        for i in range(start, end, 2):
            last = _insert_node(i // 2, data[i], data[i + 1], last)
    else:
        for i in range(end - 2, start - 1, -2):
            last = _insert_node(i // 2, data[i], data[i + 1], last)
    if last is not None and _equals(last, last.next):
        _remove_node(last)
        last = last.next
    return last


def _filter_points(start: _Node | None, end: _Node | None = None) -> _Node | None:
    if start is None:
        return start
    if end is None:
        end = start
    p = start
    while True:
        again = False
        if not p.steiner and (_equals(p, p.next) or _area(p.prev, p, p.next) == 0):
            _remove_node(p)
            p = end = p.prev
            if p is p.next:
                break
            again = True
        else:
            p = p.next
        if not again and p is end:
            break
    return end


def _z_order(x: float, y: float, min_x: float, min_y: float, inv_size: float) -> int:
    x = int((x - min_x) * inv_size)
    y = int((y - min_y) * inv_size)
    x = (x | (x << 8)) & 0x00FF00FF
    x = (x | (x << 4)) & 0x0F0F0F0F
    x = (x | (x << 2)) & 0x33333333
    x = (x | (x << 1)) & 0x55555555
    y = (y | (y << 8)) & 0x00FF00FF
    y = (y | (y << 4)) & 0x0F0F0F0F
    y = (y | (y << 2)) & 0x33333333
    y = (y | (y << 1)) & 0x55555555
    return x | (y << 1)


def _sort_linked(head: _Node) -> _Node:
    in_size = 1
    while True:
        p = head
        head = None
        tail = None
        merges = 0
        while p is not None:
            merges += 1
            q = p
            p_size = 0
            for _ in range(in_size):
                p_size += 1
                q = q.next_z
                if q is None:
                    break
            q_size = in_size
            while p_size > 0 or (q_size > 0 and q is not None):
                if p_size != 0 and (q_size == 0 or q is None or p.z <= q.z):
                    node = p
                    p = p.next_z
                    p_size -= 1
                else:
                    node = q
                    q = q.next_z
                    q_size -= 1
                if tail is not None:
                    tail.next_z = node
                else:
                    head = node
                node.prev_z = tail
                tail = node
            p = q
        tail.next_z = None
        in_size *= 2
        if merges <= 1:
            return head


def _index_curve(start: _Node, min_x: float, min_y: float, inv_size: float) -> None:
    p = start
    while True:
        if p.z == 0:
            p.z = _z_order(p.x, p.y, min_x, min_y, inv_size)
        p.prev_z = p.prev
        p.next_z = p.next
        p = p.next
        if p is start:
            break
    p.prev_z.next_z = None
    p.prev_z = None
    _sort_linked(p)


def _is_ear(ear: _Node) -> bool:
    a, b, c = ear.prev, ear, ear.next
    if _area(a, b, c) >= 0:
        return False
    ax, ay, bx, by, cx, cy = a.x, a.y, b.x, b.y, c.x, c.y
    x0, y0 = min(ax, bx, cx), min(ay, by, cy)
    x1, y1 = max(ax, bx, cx), max(ay, by, cy)
    p = c.next
    while p is not a:
        if (
            x0 <= p.x <= x1
            and y0 <= p.y <= y1
            and _point_in_triangle(ax, ay, bx, by, cx, cy, p.x, p.y)
            and _area(p.prev, p, p.next) >= 0
        ):
            return False
        p = p.next
    return True


def _is_ear_hashed(ear: _Node, min_x: float, min_y: float, inv_size: float) -> bool:
    a, b, c = ear.prev, ear, ear.next
    if _area(a, b, c) >= 0:
        return False
    ax, ay, bx, by, cx, cy = a.x, a.y, b.x, b.y, c.x, c.y
    x0, y0 = min(ax, bx, cx), min(ay, by, cy)
    x1, y1 = max(ax, bx, cx), max(ay, by, cy)
    min_z = _z_order(x0, y0, min_x, min_y, inv_size)
    max_z = _z_order(x1, y1, min_x, min_y, inv_size)

    def blocks(p: _Node) -> bool:
        return (
            x0 <= p.x <= x1
            and y0 <= p.y <= y1
            and p is not a
            and p is not c
            and _point_in_triangle(ax, ay, bx, by, cx, cy, p.x, p.y)
            and _area(p.prev, p, p.next) >= 0
        )

    p = ear.prev_z
    n = ear.next_z
    while p is not None and p.z >= min_z and n is not None and n.z <= max_z:
        if blocks(p):
            return False
        p = p.prev_z
        if blocks(n):
            return False
        n = n.next_z
    while p is not None and p.z >= min_z:
        if blocks(p):
            return False
        p = p.prev_z
    while n is not None and n.z <= max_z:
        if blocks(n):
            return False
        n = n.next_z
    return True


def _locally_inside(a: _Node, b: _Node) -> bool:
    if _area(a.prev, a, a.next) < 0:
        return _area(a, b, a.next) >= 0 and _area(a, a.prev, b) >= 0
    return _area(a, b, a.prev) < 0 or _area(a, a.next, b) < 0


def _middle_inside(a: _Node, b: _Node) -> bool:
    p = a
    inside = False
    px = (a.x + b.x) / 2
    py = (a.y + b.y) / 2
    while True:
        crosses = (p.y > py) != (p.next.y > py) and p.next.y != p.y
        if crosses and px < (p.next.x - p.x) * (py - p.y) / (p.next.y - p.y) + p.x:
            inside = not inside
        p = p.next
        if p is a:
            break
    return inside


def _intersects_polygon(a: _Node, b: _Node) -> bool:
    p = a
    while True:
        edge = (p.i, p.next.i)
        if a.i not in edge and b.i not in edge and _intersects(p, p.next, a, b):
            return True
        p = p.next
        if p is a:
            break
    return False


def _is_valid_diagonal(a: _Node, b: _Node) -> bool:
    if b.i in (a.next.i, a.prev.i) or _intersects_polygon(a, b):
        return False
    visible = (
        _locally_inside(a, b)
        and _locally_inside(b, a)
        and _middle_inside(a, b)
        and (_area(a.prev, a, b.prev) != 0 or _area(a, b.prev, b) != 0)
    )
    zero_length = _equals(a, b) and _area(a.prev, a, a.next) > 0 and _area(b.prev, b, b.next) > 0
    return visible or zero_length


def _split_polygon(a: _Node, b: _Node) -> _Node:
    a2 = _Node(a.i, a.x, a.y)
    b2 = _Node(b.i, b.x, b.y)
    an = a.next
    bp = b.prev
    a.next = b
    b.prev = a
    a2.next = an
    an.prev = a2
    b2.next = a2
    a2.prev = b2
    bp.next = b2
    b2.prev = bp
    return b2


def _cure_local_intersections(start: _Node, triangles: list[int]) -> _Node | None:
    p = start
    while True:
        a = p.prev
        b = p.next.next
        if not _equals(a, b) and _intersects(a, p, p.next, b) and _locally_inside(a, b) and _locally_inside(b, a):
            triangles.extend((a.i, p.i, b.i))
            _remove_node(p)
            _remove_node(p.next)
            p = start = b
        p = p.next
        if p is start:
            break
    return _filter_points(p)


def _split_earcut(start: _Node, triangles: list[int], min_x, min_y, inv_size) -> None:
    a = start
    while True:
        b = a.next.next
        while b is not a.prev:
            if a.i != b.i and _is_valid_diagonal(a, b):
                c = _split_polygon(a, b)
                a = _filter_points(a, a.next)
                c = _filter_points(c, c.next)
                _earcut_linked(a, triangles, min_x, min_y, inv_size, 0)
                _earcut_linked(c, triangles, min_x, min_y, inv_size, 0)
                return
            b = b.next
        a = a.next
        if a is start:
            break


def _earcut_linked(ear: _Node | None, triangles: list[int], min_x, min_y, inv_size, pass_number: int) -> None:
    if ear is None:
        return
    if pass_number == 0 and inv_size:
        _index_curve(ear, min_x, min_y, inv_size)
    stop = ear
    while ear.prev is not ear.next:
        prev = ear.prev
        nxt = ear.next
        if _is_ear_hashed(ear, min_x, min_y, inv_size) if inv_size else _is_ear(ear):
            triangles.extend((prev.i, ear.i, nxt.i))
            _remove_node(ear)
            ear = nxt.next
            stop = nxt.next
            continue
        ear = nxt
        if ear is stop:
            if pass_number == 0:
                _earcut_linked(_filter_points(ear), triangles, min_x, min_y, inv_size, 1)
            elif pass_number == 1:
                ear = _cure_local_intersections(_filter_points(ear), triangles)
                _earcut_linked(ear, triangles, min_x, min_y, inv_size, 2)
            elif pass_number == 2:
                _split_earcut(ear, triangles, min_x, min_y, inv_size)
            break


def _sector_contains_sector(m: _Node, p: _Node) -> bool:
    return _area(m.prev, m, p.prev) < 0 and _area(p.next, m, m.next) < 0


def _find_hole_bridge(hole: _Node, outer: _Node) -> _Node | None:
    p = outer
    hx, hy = hole.x, hole.y
    qx = -math.inf
    m = None
    while True:
        if hy <= p.y and hy >= p.next.y and p.next.y != p.y:
            x = p.x + (hy - p.y) * (p.next.x - p.x) / (p.next.y - p.y)
            if x <= hx and x > qx:
                qx = x
                m = p if p.x < p.next.x else p.next
                if x == hx:
                    return m
        p = p.next
        if p is outer:
            break
    if m is None:
        return None
    stop = m
    mx, my = m.x, m.y
    tan_min = math.inf
    p = m
    while True:
        if (
            hx >= p.x >= mx
            and hx != p.x
            and _point_in_triangle(hx if hy < my else qx, hy, mx, my, qx if hy < my else hx, hy, p.x, p.y)
        ):
            tan = abs(hy - p.y) / (hx - p.x)
            if _locally_inside(p, hole) and (
                tan < tan_min or (tan == tan_min and (p.x > m.x or (p.x == m.x and _sector_contains_sector(m, p))))
            ):
                m = p
                tan_min = tan
        p = p.next
        if p is stop:
            break
    return m


def _eliminate_hole(hole: _Node, outer: _Node) -> _Node:
    bridge = _find_hole_bridge(hole, outer)
    if bridge is None:
        return outer
    bridge_reverse = _split_polygon(bridge, hole)
    _filter_points(bridge_reverse, bridge_reverse.next)
    return _filter_points(bridge, bridge.next)


def _get_leftmost(start: _Node) -> _Node:
    p = start
    leftmost = start
    while True:
        if p.x < leftmost.x or (p.x == leftmost.x and p.y < leftmost.y):
            leftmost = p
        p = p.next
        if p is start:
            break
    return leftmost


def _eliminate_holes(data: list[float], hole_indices: list[int], outer: _Node) -> _Node:
    queue = []
    for position, hole_start in enumerate(hole_indices):
        start = hole_start * 2
        end = hole_indices[position + 1] * 2 if position < len(hole_indices) - 1 else len(data)
        ring = _linked_list(data, start, end, False)
        if ring is None:
            continue
        if ring is ring.next:
            ring.steiner = True
        queue.append(_get_leftmost(ring))
    queue.sort(key=lambda node: (node.x, node.y))
    for hole in queue:
        outer = _eliminate_hole(hole, outer)
    return outer


def earcut(data: list[float], hole_indices: list[int] | None = None) -> list[int]:
    """Triangulate a polygon with holes, a port of Mapbox earcut.

    Args:
        data: Flat ``x, y`` coordinates of the outer ring followed by the hole rings.
        hole_indices: Vertex index at which each hole ring starts, or ``None`` without holes.

    Returns:
        Flat vertex indices, three per triangle.
    """
    hole_indices = hole_indices or []
    outer_length = hole_indices[0] * 2 if hole_indices else len(data)
    outer = _linked_list(data, 0, outer_length, True)
    triangles: list[int] = []
    if outer is None or outer.next is outer.prev:
        return triangles
    min_x = min_y = 0.0
    inv_size = 0.0
    if hole_indices:
        outer = _eliminate_holes(data, hole_indices, outer)
    if len(data) > _HASH_THRESHOLD * 2:
        xs = data[0:outer_length:2]
        ys = data[1:outer_length:2]
        min_x, min_y = min(xs), min(ys)
        extent = max(max(xs) - min_x, max(ys) - min_y)
        inv_size = _Z_RANGE / extent if extent != 0 else 0.0
    _earcut_linked(outer, triangles, min_x, min_y, inv_size, 0)
    return triangles


def _signed_area(ring: np.ndarray) -> float:
    x = ring[:, 0]
    y = ring[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _is_convex(ring: np.ndarray) -> bool:
    """Return whether a counter-clockwise ring turns strictly left at every vertex.

    Args:
        ring: ``(N, 2)`` ring vertices without a repeated closing vertex.

    Returns:
        ``True`` when a fan from any vertex has no degenerate triangle.
    """
    first = np.roll(ring, -1, axis=0) - ring
    second = np.roll(ring, -2, axis=0) - ring
    turns = first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]
    return bool(np.all(turns > _EPSILON))


def _fan_triangles(count: int) -> np.ndarray:
    fan = np.arange(1, count - 1, dtype=np.int32)
    return np.stack((np.zeros_like(fan), fan, fan + 1), axis=1)


def earclip_polygon_with_holes(outer: np.ndarray, holes: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Triangulate a polygon with holes.

    Args:
        outer: ``(N, 2)`` outer ring without a repeated closing vertex, any winding.
        holes: ``(M, 2)`` hole rings without repeated closing vertices, any winding.

    Returns:
        ``(V, 2)`` float64 vertices, which are the input rings concatenated, and ``(T, 3)`` int32
        counter-clockwise triangles indexing them.
    """
    outer = np.asarray(outer, dtype=np.float64).reshape(-1, 2)
    if outer.shape[0] < 3:
        return outer, np.zeros((0, 3), dtype=np.int32)
    if _signed_area(outer) < 0:
        outer = outer[::-1]
    rings = [outer] + [np.asarray(hole, dtype=np.float64).reshape(-1, 2) for hole in holes]
    rings = [ring for ring in rings if ring.shape[0] >= 3]
    if len(rings) == 1 and _is_convex(outer):
        return outer, _fan_triangles(outer.shape[0])
    vertices = np.concatenate(rings, axis=0)
    hole_indices = list(np.cumsum([ring.shape[0] for ring in rings[:-1]])) if len(rings) > 1 else []
    flat = earcut(vertices.reshape(-1).tolist(), [int(index) for index in hole_indices])
    triangles = np.asarray(flat, dtype=np.int32).reshape(-1, 3)
    if triangles.shape[0]:
        corners = vertices[triangles]
        first = corners[:, 1] - corners[:, 0]
        second = corners[:, 2] - corners[:, 0]
        clockwise = first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0] < 0
        triangles[clockwise] = triangles[clockwise][:, ::-1]
    return vertices, triangles


def triangulate_shapely_polygon(polygon: Polygon) -> tuple[np.ndarray, np.ndarray]:
    """Triangulate a shapely polygon, holes included.

    Args:
        polygon: Valid polygon.

    Returns:
        ``(V, 2)`` float64 vertices and ``(T, 3)`` int32 counter-clockwise triangles indexing them.
    """
    oriented = orient(polygon, 1.0)
    outer = np.asarray(oriented.exterior.coords)[:-1]
    holes = [np.asarray(interior.coords)[:-1] for interior in oriented.interiors]
    return earclip_polygon_with_holes(outer, holes)
