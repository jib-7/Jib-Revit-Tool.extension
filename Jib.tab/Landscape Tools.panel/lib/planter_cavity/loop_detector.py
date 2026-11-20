# -*- coding: utf-8 -*-
"""Detect closed loops (bounded faces) in a planar Graph."""
from __future__ import division
import math

from .models import BoundaryLoop, LoopEdge, signed_area
from .point_in_polygon import point_in_polygon


def _trace_cycles(graph, edge_ids):
    nodes, edges = graph.nodes, graph.edges
    out = {}
    for ei in edge_ids:
        e = edges[ei]
        ax, ay = nodes[e.a]
        bx, by = nodes[e.b]
        out.setdefault(e.a, []).append((math.atan2(by - ay, bx - ax), 2 * ei))
        out.setdefault(e.b, []).append((math.atan2(ay - by, ax - bx), 2 * ei + 1))
    pos = {}
    for n, lst in out.items():
        lst.sort()
        for idx, (ang, h) in enumerate(lst):
            pos[h] = idx

    def dest(h):
        e = edges[h >> 1]
        return e.b if (h & 1) == 0 else e.a

    visited = set()
    cycles = []
    for ei in edge_ids:
        for h in (2 * ei, 2 * ei + 1):
            if h in visited:
                continue
            cyc = []
            cur = h
            while cur not in visited:
                visited.add(cur)
                cyc.append(cur)
                lst = out[dest(cur)]
                cur = lst[(pos[cur ^ 1] - 1) % len(lst)][1]
            cycles.append(cyc)
    return cycles


def _split_simple(cycle, origin):
    stack_h = []
    pos = {}
    loops = []
    for h in cycle:
        n = origin(h)
        if n in pos:
            k = pos[n]
            sub = stack_h[k:]
            loops.append(sub)
            for hh in sub:
                pos.pop(origin(hh), None)
            stack_h = stack_h[:k]
        pos[n] = len(stack_h)
        stack_h.append(h)
    if stack_h:
        loops.append(stack_h)
    return loops


def find_loops(graph, min_area=0.0):
    """Return all bounded (counter-clockwise, simple) loops of the graph."""
    edge_ids = graph.core_edge_ids()
    if not edge_ids:
        return []
    nodes, edges = graph.nodes, graph.edges

    def origin(h):
        e = edges[h >> 1]
        return e.a if (h & 1) == 0 else e.b

    result = []
    for cyc in _trace_cycles(graph, edge_ids):
        for sub in _split_simple(cyc, origin):
            if len(sub) < 3:
                continue
            pts = [nodes[origin(h)] for h in sub]
            area = signed_area(pts)
            if area <= min_area:
                continue
            ledges = []
            for h in sub:
                e = edges[h >> 1]
                a = nodes[origin(h)]
                dn = e.b if (h & 1) == 0 else e.a
                ledges.append(LoopEdge(a, nodes[dn], e.arc, e.synthetic, e.top))
            result.append(BoundaryLoop(ledges))
    return result


def loops_containing(loops, pt, tol=0.0):
    hits = [lp for lp in loops if point_in_polygon(pt, lp.points, tol) >= 0]
    hits.sort(key=lambda lp: lp.area)
    return hits


def smallest_loop_containing(graph, pt, tol=0.0, min_area=0.0):
    hits = loops_containing(find_loops(graph, min_area), pt, tol)
    return hits[0] if hits else None
