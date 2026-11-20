# -*- coding: utf-8 -*-
"""Planar curve network: noding of intersecting curves into a graph."""
from __future__ import division
import math

from .models import (dist, point_seg_dist, v_sub, v_cross)


class Edge(object):
    __slots__ = ('a', 'b', 'arc', 'synthetic', 'top', 'base')

    def __init__(self, a, b, arc=None, synthetic=False, top=False, base=-1):
        self.a = a
        self.b = b
        self.arc = arc
        self.synthetic = synthetic
        self.top = top
        self.base = base


class Graph(object):
    def __init__(self, nodes, edges):
        self.nodes = nodes      # list of (u, v)
        self.edges = edges      # list of Edge

    def copy(self):
        return Graph(list(self.nodes),
                     [Edge(e.a, e.b, e.arc, e.synthetic, e.top, e.base) for e in self.edges])

    def adjacency(self):
        adj = {}
        for i, e in enumerate(self.edges):
            adj.setdefault(e.a, []).append(i)
            adj.setdefault(e.b, []).append(i)
        return adj

    def degrees(self):
        deg = {}
        for e in self.edges:
            deg[e.a] = deg.get(e.a, 0) + 1
            deg[e.b] = deg.get(e.b, 0) + 1
        return deg

    def dangling_nodes(self):
        return [n for n, d in self.degrees().items() if d == 1]

    def core_edge_ids(self):
        """Edge ids remaining after iteratively pruning dangling edges."""
        adj = self.adjacency()
        alive = set(range(len(self.edges)))
        deg = dict((n, len(l)) for n, l in adj.items())
        stack = [n for n, d in deg.items() if d <= 1]
        while stack:
            n = stack.pop()
            for ei in adj.get(n, ()):
                if ei in alive:
                    alive.discard(ei)
                    e = self.edges[ei]
                    other = e.b if e.a == n else e.a
                    deg[other] -= 1
                    if deg[other] <= 1:
                        stack.append(other)
            deg[n] = 0
        return sorted(alive)


class _NodeIndex(object):
    def __init__(self, tol):
        self.tol = tol
        self.cell = tol if tol > 0 else 1e-6
        self.cells = {}
        self.nodes = []

    def get(self, pt):
        cx = int(math.floor(pt[0] / self.cell))
        cy = int(math.floor(pt[1] / self.cell))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for nid in self.cells.get((cx + dx, cy + dy), ()):
                    q = self.nodes[nid]
                    if math.hypot(q[0] - pt[0], q[1] - pt[1]) <= self.tol:
                        return nid
        nid = len(self.nodes)
        self.nodes.append((pt[0], pt[1]))
        self.cells.setdefault((cx, cy), []).append(nid)
        return nid


def _pair_splits(p0, p1, q0, q1, tol):
    res_a, res_b = [], []
    for q in (q0, q1):
        d, t = point_seg_dist(q, p0, p1)
        if d <= tol:
            res_a.append((t, q))
    for p in (p0, p1):
        d, t = point_seg_dist(p, q0, q1)
        if d <= tol:
            res_b.append((t, p))
    r = v_sub(p1, p0)
    s = v_sub(q1, q0)
    lr = math.hypot(r[0], r[1])
    ls = math.hypot(s[0], s[1])
    den = v_cross(r, s)
    if lr > 0 and ls > 0 and abs(den) > 1e-9 * lr * ls:
        qp = v_sub(q0, p0)
        t = v_cross(qp, s) / den
        u = v_cross(qp, r) / den
        if t * lr > tol and (1 - t) * lr > tol and u * ls > tol and (1 - u) * ls > tol:
            pt = (p0[0] + r[0] * t, p0[1] + r[1] * t)
            res_a.append((t, pt))
            res_b.append((u, pt))
    return res_a, res_b


def build_graph(primitives, snap_tol, arc_tol):
    """Node all primitives against each other and return a Graph."""
    pieces = []
    for prim in primitives:
        for (a, b, arc) in prim.pieces(arc_tol):
            if dist(a, b) > snap_tol:
                pieces.append((a, b, arc))
    n = len(pieces)
    if n == 0:
        return Graph([], [])
    lengths = sorted(dist(p[0], p[1]) for p in pieces)
    cell = max(lengths[n // 2] * 2.0, snap_tol * 50.0, 1e-3)
    grid = {}
    big = []
    for i, (a, b, arc) in enumerate(pieces):
        x0 = min(a[0], b[0]) - snap_tol
        x1 = max(a[0], b[0]) + snap_tol
        y0 = min(a[1], b[1]) - snap_tol
        y1 = max(a[1], b[1]) + snap_tol
        ix0, ix1 = int(math.floor(x0 / cell)), int(math.floor(x1 / cell))
        iy0, iy1 = int(math.floor(y0 / cell)), int(math.floor(y1 / cell))
        if (ix1 - ix0 + 1) * (iy1 - iy0 + 1) > 2500:
            big.append(i)
            continue
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                grid.setdefault((ix, iy), []).append(i)
    pairs = set()
    for items in grid.values():
        m = len(items)
        for x in range(m):
            for y in range(x + 1, m):
                i, j = items[x], items[y]
                pairs.add((i, j) if i < j else (j, i))
    for i in big:
        for j in range(n):
            if j != i:
                pairs.add((i, j) if i < j else (j, i))
    splits = [[] for _ in range(n)]
    for (i, j) in pairs:
        ra, rb = _pair_splits(pieces[i][0], pieces[i][1], pieces[j][0], pieces[j][1], snap_tol)
        splits[i].extend(ra)
        splits[j].extend(rb)
    index = _NodeIndex(snap_tol)
    edges = []
    seen = {}
    for i, (a, b, arc) in enumerate(pieces):
        seq = [(0.0, index.get(a))]
        for (t, pt) in splits[i]:
            seq.append((t, index.get(pt)))
        seq.append((1.0, index.get(b)))
        seq.sort(key=lambda x: x[0])
        for k in range(len(seq) - 1):
            na, nb = seq[k][1], seq[k + 1][1]
            if na == nb:
                continue
            key = (na, nb) if na < nb else (nb, na)
            if key in seen:
                ex = edges[seen[key]]
                if ex.arc is None and arc is not None:
                    ex.arc = arc
                continue
            seen[key] = len(edges)
            edges.append(Edge(na, nb, arc, False, False, len(edges)))
    return Graph(index.nodes, edges)
