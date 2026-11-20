# -*- coding: utf-8 -*-
"""Closes small openings (open planter top, drainage gaps) around a point.

Strategy
--------
1. Candidate "chords" are generated between graph vertices that are visible
   from the clicked point (vertex-to-vertex) and from dangling ends to nearby
   edges (perpendicular / horizontal feet).  Only chords shorter than the
   configured limits are produced.  Near-horizontal chords above the click
   that span it ("top closures") may be as long as ``max_top_gap``; every
   other chord is limited to ``max_gap``.
2. Chords are tried shortest-first; the smallest prefix that encloses the
   click point is found by galloping + binary search and then reduced to a
   minimal chord set (delta debugging).  Unrelated chords therefore never
   survive.
3. Alternative minimal solutions of (nearly) equal cost are reported so the
   caller can show a selection dialog.
"""
from __future__ import division
import math

from .curve_graph import Edge
from .loop_detector import find_loops, loops_containing
from .models import dist, point_seg_dist, seg_intersects, BoundaryLoop


class Chord(object):
    def __init__(self, a_node, p, q, top, b_node=None, foot_edge=None):
        self.a_node = a_node
        self.b_node = b_node
        self.foot_edge = foot_edge
        self.p = p
        self.q = q
        self.top = top
        self.length = dist(p, q)
        self.key = (round(p[0], 5), round(p[1], 5), round(q[0], 5), round(q[1], 5))


class ClosureSolution(object):
    def __init__(self, chords, loop):
        self.chords = chords
        self.loop = loop
        self.cost = sum(c.length for c in chords)
        self.loop.bridges = [{'length': c.length, 'top': c.top} for c in chords]


# ------------------------------------------------------------ graph helpers
def _insert_on_edge(g, pt, base, tol):
    for i, e in enumerate(g.edges):
        if e.base != base:
            continue
        pa, pb = g.nodes[e.a], g.nodes[e.b]
        d, t = point_seg_dist(pt, pa, pb)
        if d > tol * 2.0:
            continue
        if dist(pt, pa) <= tol:
            return e.a
        if dist(pt, pb) <= tol:
            return e.b
        nid = len(g.nodes)
        g.nodes.append((pt[0], pt[1]))
        old_b = e.b
        e.b = nid
        g.edges.append(Edge(nid, old_b, e.arc, e.synthetic, e.top, e.base))
        return nid
    return None


def apply_chords(graph, chords, tol):
    g = graph.copy()
    for c in chords:
        na = c.a_node
        nb = c.b_node
        if nb is None:
            nb = _insert_on_edge(g, c.q, c.foot_edge, tol)
            if nb is None:
                continue
        if na == nb:
            continue
        g.edges.append(Edge(na, nb, None, True, c.top, -1))
    return g


def enclosing_loop(graph, chords, p, cfg):
    g = apply_chords(graph, chords, cfg.snap_tol) if chords else graph
    hits = loops_containing(find_loops(g, cfg.min_area), p, 0.0)
    return hits[0] if hits else None


# ------------------------------------------------------------- candidates
def _sight_clear(pa, pb, graph, ignore_nodes, tol, ignore_edge=None):
    nodes = graph.nodes
    for i, e in enumerate(graph.edges):
        if i == ignore_edge or e.a in ignore_nodes or e.b in ignore_nodes:
            continue
        if seg_intersects(pa, pb, nodes[e.a], nodes[e.b], tol):
            return False
    return True


def _chord_clear(pa, pb, graph, used, ignore_nodes, tol, ignore_edge=None):
    if not _sight_clear(pa, pb, graph, ignore_nodes, tol, ignore_edge):
        return False
    for n in used:
        if n in ignore_nodes:
            continue
        if point_seg_dist(graph.nodes[n], pa, pb)[0] <= tol * 2.0:
            return False
    return True


def _classify(pa, pb, p, cfg):
    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
    length = math.hypot(dx, dy)
    if length <= 0:
        return length, False, 0.0
    ang = abs(math.atan2(dy, dx))
    ang = min(ang, math.pi - ang)
    top = (ang <= cfg.top_angle and min(pa[1], pb[1]) >= p[1] - cfg.snap_tol and
           min(pa[0], pb[0]) < p[0] < max(pa[0], pb[0]))
    return length, top, (cfg.max_top_gap if top else cfg.max_gap)


def generate_candidates(graph, p, cfg):
    nodes, edges = graph.nodes, graph.edges
    tol = cfg.snap_tol
    used = set()
    for e in edges:
        used.add(e.a)
        used.add(e.b)
    near = sorted((dist(p, nodes[n]), n) for n in used if dist(p, nodes[n]) <= cfg.search_radius)
    vis = []
    for d, n in near[:400]:
        if _sight_clear(p, nodes[n], graph, (n,), tol):
            vis.append(n)
        if len(vis) >= cfg.max_visible_nodes:
            break
    connected = set()
    for e in edges:
        connected.add((min(e.a, e.b), max(e.a, e.b)))
    cands = {}
    for i in range(len(vis)):
        for j in range(i + 1, len(vis)):
            a, b = vis[i], vis[j]
            if (min(a, b), max(a, b)) in connected:
                continue
            length, top, limit = _classify(nodes[a], nodes[b], p, cfg)
            if length <= tol or length > limit:
                continue
            c = Chord(a, nodes[a], nodes[b], top, b_node=b)
            cands[c.key] = c
    deg = graph.degrees()
    for d in vis:
        if deg.get(d, 0) != 1:
            continue
        pd = nodes[d]
        for ei, e in enumerate(edges):
            if e.a == d or e.b == d:
                continue
            pa, pb = nodes[e.a], nodes[e.b]
            dd, t = point_seg_dist(pd, pa, pb)
            feet = []
            if 0.0 < t < 1.0 and dd > tol:   # perpendicular foot
                feet.append(((pa[0] + (pb[0] - pa[0]) * t, pa[1] + (pb[1] - pa[1]) * t), False))
            if pd[1] >= p[1] - tol and abs(pb[1] - pa[1]) > 1e-9:   # horizontal foot (top)
                th = (pd[1] - pa[1]) / (pb[1] - pa[1])
                if 0.0 < th < 1.0:
                    feet.append(((pa[0] + (pb[0] - pa[0]) * th, pd[1]), True))
            for f, horiz in feet:
                if dist(f, pa) <= tol or dist(f, pb) <= tol:
                    continue
                length, top, limit = _classify(pd, f, p, cfg)
                if length <= tol or length > limit:
                    continue
                if horiz and not top:
                    continue
                c = Chord(d, pd, f, top, None, e.base)
                cands.setdefault(c.key, c)
    out = list(cands.values())
    out.sort(key=lambda c: (c.length, c.key))
    return out, used


class _Search(object):
    """Incrementally filters candidate chords (clear of obstacles / each other)."""

    def __init__(self, graph, cands, used, cfg):
        self.graph = graph
        self.cands = cands
        self.used = used
        self.cfg = cfg
        self.pos = 0
        self.accepted = []     # (index, chord)

    def extend_to(self, k):
        tol = self.cfg.snap_tol
        k = min(k, len(self.cands))
        while self.pos < k:
            c = self.cands[self.pos]
            ok = _chord_clear(c.p, c.q, self.graph, self.used,
                              set([c.a_node] + ([c.b_node] if c.b_node is not None else [])),
                              tol, ignore_edge=self._foot_edge_index(c))
            if ok:
                for (_, o) in self.accepted:
                    if seg_intersects(c.p, c.q, o.p, o.q, tol) and not self._share_end(c, o):
                        ok = False
                        break
            if ok:
                self.accepted.append((self.pos, c))
            self.pos += 1

    def _foot_edge_index(self, c):
        if c.foot_edge is None:
            return None
        return c.foot_edge

    @staticmethod
    def _share_end(c, o):
        ends_c = set([c.a_node, c.b_node]) - set([None])
        ends_o = set([o.a_node, o.b_node]) - set([None])
        if ends_c & ends_o:
            # sharing a node is fine unless the chords overlap collinearly
            return True
        return False

    def prefix(self, k):
        self.extend_to(k)
        return [c for (i, c) in self.accepted if i < k]


def _ddmin(items, test):
    n = 2
    items = list(items)
    while len(items) >= 2:
        chunk = max(1, int(math.ceil(len(items) / float(n))))
        subsets = [items[i:i + chunk] for i in range(0, len(items), chunk)]
        reduced = False
        for s in subsets:
            comp = [x for x in items if x not in s]
            if comp and test(comp):
                items = comp
                n = max(n - 1, 2)
                reduced = True
                break
        if not reduced:
            if n >= len(items):
                break
            n = min(len(items), n * 2)
    if len(items) == 1 and test([]):
        return []
    return items


def _solve(graph, p, cfg, cands, used, banned):
    usable = [c for c in cands if c.key not in banned]
    if not usable:
        return None
    search = _Search(graph, usable, used, cfg)

    def enclosed(chords):
        return enclosing_loop(graph, chords, p, cfg) is not None

    k = min(4, len(usable))
    lo = 0
    while True:
        if enclosed(search.prefix(k)):
            break
        if k >= len(usable):
            return None
        lo = k
        k = min(len(usable), k * 2)
    hi = k
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if enclosed(search.prefix(mid)):
            hi = mid
        else:
            lo = mid
    chords = _ddmin(search.prefix(hi), enclosed)
    loop = enclosing_loop(graph, chords, p, cfg)
    if loop is None:
        return None
    return ClosureSolution(chords, loop)


def _level(c):
    return (c.p[1] + c.q[1]) / 2.0


def _lift_top(graph, p, cfg, cands, used, sol):
    """Prefer the highest top-closure chord when closures are nested.

    A planter cavity with a stepped / lipped top is closed at the very top of
    the walls rather than at the narrowest level.
    """
    cur = sol
    for _ in range(8):
        tops = [c for c in cur.chords if c.top]
        if len(tops) != 1:
            break
        t = tops[0]
        lvl = _level(t)
        banned = frozenset(c.key for c in cands if c.top and (
            _level(c) <= lvl + cfg.level_tol or abs(c.p[1] - c.q[1]) > cfg.level_tol))
        alt = _solve(graph, p, cfg, cands, used, banned)
        if alt is None:
            break
        at = [c for c in alt.chords if c.top]
        if len(at) != 1:
            break
        same_other = (set(c.key for c in alt.chords if not c.top) ==
                      set(c.key for c in cur.chords if not c.top))
        if (same_other and _level(at[0]) > _level(t) + cfg.level_tol and
                alt.loop.area > cur.loop.area and alt.cost <= cur.cost + cfg.max_gap):
            cur = alt
        else:
            break
    return cur


def find_closures(graph, p, cfg):
    """Return a list of ClosureSolution (best first); empty if none."""
    cands, used = generate_candidates(graph, p, cfg)
    if not cands:
        return []
    best = _solve(graph, p, cfg, cands, used, frozenset())
    if best is None:
        return []
    best = _lift_top(graph, p, cfg, cands, used, best)
    sols = [best]
    sigs = set([best.loop.signature(4)])
    best_other = set(c.key for c in best.chords if not c.top)
    for ch in best.chords:
        alt = _solve(graph, p, cfg, cands, used, frozenset([ch.key]))
        if alt is None:
            continue
        sig = alt.loop.signature(4)
        if sig in sigs:
            continue
        if set(c.key for c in alt.chords if not c.top) == best_other:
            continue    # differs only in the top closure level: resolved by _lift_top
        if alt.cost <= best.cost + cfg.ambiguity_tol:
            sols.append(alt)
            sigs.add(sig)
    sols.sort(key=lambda s: s.cost)
    return sols
