"""Orthogonal (Manhattan) routing on a grid.

Pipes in construction drawings are drawn orthogonally, so the router
only moves in x / y. Obstacles are expanded by half a cell so a pipe
never passes through a shaft / column in the draft.
"""
from __future__ import annotations

import heapq

from .models import Point, Rect


def _blocked(obstacles: list[Rect], step: float) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for o in obstacles:
        x0 = int((o.x - step / 2) // step)
        x1 = int((o.x_max + step / 2) // step)
        y0 = int((o.y - step / 2) // step)
        y1 = int((o.y_max + step / 2) // step)
        for gx in range(x0, x1 + 1):
            for gy in range(y0, y1 + 1):
                cells.add((gx, gy))
    return cells


def route(start: Point, end: Point, obstacles: list[Rect],
          width: float, depth: float, step: float = 0.5) -> list[Point]:
    """A* route from start to end. Returns at least [start, end]."""
    def snap(p: Point) -> tuple[int, int]:
        return (round(p.x / step), round(p.y / step))

    s, t = snap(start), snap(end)
    blocked = _blocked(obstacles, step)
    blocked.discard(s)
    blocked.discard(t)
    max_x, max_y = int(width / step), int(depth / step)

    def h(a: tuple[int, int]) -> float:
        return abs(a[0] - t[0]) + abs(a[1] - t[1])

    open_heap: list[tuple[float, float, tuple[int, int]]] = [(h(s), 0, s)]
    came: dict[tuple[int, int], tuple[int, int] | None] = {s: None}
    cost: dict[tuple[int, int], float] = {s: 0}
    while open_heap:
        _, g, cur = heapq.heappop(open_heap)
        if cur == t:
            break
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (cur[0] + dx, cur[1] + dy)
            if not (0 <= nxt[0] <= max_x and 0 <= nxt[1] <= max_y):
                continue
            if nxt in blocked:
                continue
            ng = g + 1
            if nxt not in cost or ng < cost[nxt]:
                cost[nxt] = ng
                came[nxt] = cur
                heapq.heappush(open_heap, (ng + h(nxt), ng, nxt))
    if t not in came:
        # No grid path (e.g. fully blocked): fall back to a straight
        # L-shaped draft route so the failure is visible in validation,
        # rather than silently dropping the fixture.
        return [start, Point(end.x, start.y), end]
    path: list[tuple[int, int]] = []
    cur: tuple[int, int] | None = t
    while cur is not None:
        path.append(cur)
        cur = came[cur]
    path.reverse()
    # Simplify collinear points, keep start / end exact.
    pts = [Point(x * step, y * step) for x, y in path]
    simplified: list[Point] = [pts[0]]
    for prev, cur_p, nxt in zip(pts, pts[1:], pts[2:]):
        if (prev.x == cur_p.x == nxt.x) or (prev.y == cur_p.y == nxt.y):
            continue
        simplified.append(cur_p)
    simplified.append(pts[-1])
    # Restore exact endpoints for drawing accuracy.
    simplified[0] = start
    simplified[-1] = end
    return simplified
