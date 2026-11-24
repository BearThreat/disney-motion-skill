#!/usr/bin/env python3
"""motion_check: diagnostic checks for Disney-style motion. Python 3.9+, standard library only.

Modes:
  motion_check.py tracks FILE.json [--json]   check animation channels sampled once per frame
  motion_check.py bezier "x1,y1,x2,y2"         overshoot and shape of a CSS cubic-bezier easing
  motion_check.py spring --stiffness K --damping C [--mass M]
                                              damping ratio, overshoot and 2% settle time of a spring

Exit codes: 0 = no FAIL, 1 = at least one FAIL (tracks mode), 2 = invalid input (message on stderr).

A passing report means only that these heuristics found no problem in the samples you gave.
It does not judge appeal; watch the result at its real frame rate as well.

Track file: see examples/tracks.example.json for a copyable file. Fields:
  fps       frames per second of the samples (default 24)
  context   "character" | "object" | "ui" (default "character")
  dial      exaggeration level from SKILL.md (default 1.0); scales the character overshoot limit
  tracks    {"name": [one number per frame, ...]}; every track has the same length (>= 3)
Optional groups (each name must exist in tracks):
  volume    [["sx", "sy"]] or [["sx", "sy", "sz"]]   squash groups whose product should stay near 1
  chains    [["root", "link1", "link2"]]             parent -> child; children should lag their parent
  paths     [["x", "y"]]                             2D positions that should travel in arcs
  mirrors   [["armL", "armR"]]                       left/right pairs that should not move as twins
  contacts  [22, 40]                                 frames where a sharp path corner is allowed
  prep      {"head": ["body"]}                       name prefixes whose wind-up counts for another prefix
  exempt    {"ease": ["ball.x"], "jelly": ["*"]}     checks to skip per track, for intended motion
  y_down    true when y grows downward (screen space)

Checks, and where they run:
  ease          every non-scale track     FAIL when a move runs at constant speed from start to stop
  overshoot     every track               FAIL when a move passes its rest value by more than the limit
                                          (ui 10%, object 25%, character 35% x dial); skipped for wags
  jelly         every track               WARN when swings do not shrink, or UI wobbles more than twice
  anticipation  character context         WARN when a big move has no small opposite move just before it
                                          (in a track with the same prefix, or a prefix named in prep)
  volume        volume groups             FAIL when the product leaves 1 by more than 6%
  squash_overuse volume groups            WARN when squash is active on more than 60% of frames
  overlap       chains                    FAIL when every link moves on its parent's frame, WARN for some
  arcs          paths                     WARN on straight travel or a sharp corner away from contacts
  twins         mirrors                   WARN when a pair moves identically (either axis polarity)
  dead_hold     character context         WARN when every track freezes for more than 0.5 s
"""
from __future__ import annotations

import argparse
import json
import math
import sys

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
CONTEXTS = ("ui", "object", "character")
OVERSHOOT_LIMIT = {"ui": 0.10, "object": 0.25, "character": 0.35}


class BadInput(ValueError):
    pass


def finding(check, level, msg, track=None):
    return {"check": check, "level": level, "track": track, "msg": msg}


def velocity(xs):
    return [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]


def track_range(xs):
    return (max(xs) - min(xs)) if xs else 0.0


def still_eps(xs):
    return max(track_range(xs) * 1e-3, 1e-9)


def segments(xs, eps):
    """Monotonic moves as (start_frame, end_frame, direction). Still frames and reversals end a move."""
    v = velocity(xs)
    segs, start, direction = [], 0, 0
    for i, dv in enumerate(v):
        d = 0 if abs(dv) <= eps else (1 if dv > 0 else -1)
        if d != direction:
            if direction != 0:
                segs.append((start, i, direction))
            start, direction = i, d
    if direction != 0:
        segs.append((start, len(v), direction))
    return segs


def prefix(name):
    return name.split(".", 1)[0]


# ---------------------------------------------------------------- per-track checks

def check_ease(name, xs, fps):
    """A move that starts and stops at full speed reads as mechanical."""
    out = []
    min_steps = max(3, round(0.1 * fps))
    rng = track_range(xs)
    for s, e, _ in segments(xs, still_eps(xs)):
        if e - s < min_steps or abs(xs[e] - xs[s]) < 0.1 * rng:
            continue  # too short or too small to read as a move
        speeds = [abs(x) for x in velocity(xs[s:e + 1])]
        peak = max(speeds)
        if speeds[0] < 0.85 * peak or speeds[-1] < 0.85 * peak:
            continue  # at least one end eases
        mean = sum(speeds) / len(speeds)
        cv = math.sqrt(sum((x - mean) ** 2 for x in speeds) / len(speeds)) / mean
        if cv < 0.1:
            out.append(finding("ease", FAIL, f"frames {s}-{e}: constant speed from start to stop. Add slow in / "
                                             "slow out, or exempt it if it is ballistic or mechanical.", name))
        else:
            out.append(finding("ease", WARN, f"frames {s}-{e}: starts and stops at full speed. Ease at least one "
                                             "end.", name))
    return out


def rests(xs, fps):
    """Each move that ends in a hold, as (move_start_frame, rest_frame)."""
    eps = still_eps(xs)
    v = velocity(xs)
    still = [abs(x) <= eps for x in v]
    hold_min = max(2, round(0.08 * fps))
    beats, i, n = [], 0, len(v)
    move_start = None
    while i < n:
        if not still[i]:
            if move_start is None:
                move_start = i
            i += 1
            continue
        j = i
        while j < n and still[j]:
            j += 1
        if move_start is not None and (j - i >= hold_min or j == n):
            beats.append((move_start, i))  # the move ends at frame i, which starts the hold
            move_start = None
        i = j
    return beats


def check_settle(name, xs, fps, context, dial):
    """Overshoot past each rest value, and whether the swings around it die down."""
    out = []
    limit = OVERSHOOT_LIMIT[context] * (dial if context == "character" else 1.0)
    for a, b in rests(xs, fps):
        start, target = xs[a], xs[b]
        disp = target - start
        reach = max(abs(x - start) for x in xs[a:b + 1])
        d = [x - target for x in xs[a:b + 1]]
        ref = max(abs(disp), max(abs(x) for x in d))
        if ref <= 1e-9:
            continue
        tol = 0.02 * ref
        peaks, side, cur = [], 0, 0.0  # side runs, tracked across samples that sit on the target
        for x in d:
            if abs(x) <= tol:
                continue
            s = 1 if x > 0 else -1
            if s != side and side != 0:
                peaks.append(cur)
                cur = 0.0
            side = s
            cur = max(cur, abs(x))
        if side != 0:
            peaks.append(cur)
        crossings = len(peaks) - 1 if peaks else 0
        wag = abs(disp) < 0.25 * reach  # returns to where it started: a wag, shake or pulse
        if not wag:
            sign = 1 if disp > 0 else -1
            over = max(0.0, max(sign * x for x in d)) / abs(disp)
            if over > limit and not (context == "character" and crossings >= 3):
                out.append(finding("overshoot", FAIL,
                                   f"frames {a}-{b}: passes its rest value by {over:.0%} of the move (limit "
                                   f"{limit:.0%} for {context}, dial {dial}).", name))
        if context == "ui" and crossings > 2:
            out.append(finding("jelly", WARN, f"frames {a}-{b}: crosses its rest value {crossings} times. UI should "
                                              "settle in 1-2.", name))
        big = [p for p in peaks if p > 0.05 * ref]
        big = big[big.index(max(big)):] if big else big  # free swings after the strongest push
        ratios = sorted(big[i + 1] / big[i] for i in range(len(big) - 1))
        if len(ratios) >= 3 and ratios[len(ratios) // 2] > 0.85:
            out.append(finding("jelly", WARN,
                               f"frames {a}-{b}: {len(big)} swings that barely shrink (median ratio "
                               f"{ratios[len(ratios) // 2]:.2f}). Each swing should be clearly smaller than the "
                               "last (ratio 0.7 or less), then settle.", name))
    return out


# ---------------------------------------------------------------- group checks

def anticipation_events(xs, fps):
    """Big moves (start frames) and wind-ups (end frames) in one track."""
    rng = track_range(xs)
    if rng <= 0:
        return [], []
    segs = segments(xs, still_eps(xs))
    gap = max(2, round(0.1 * fps))
    majors, preps = [], []
    for k, (s, e, d) in enumerate(segs):
        amp = abs(xs[e] - xs[s])
        prev = segs[k - 1] if k else None
        pamp = abs(xs[prev[1]] - xs[prev[0]]) if prev else 0.0
        joined = prev is not None and prev[2] == -d and s - prev[1] <= gap
        if joined and 0.03 * amp <= pamp <= 0.6 * amp:
            preps.append(prev[1])
        if amp < 0.4 * rng:
            continue
        if joined and pamp > 0.6 * amp:
            continue  # a swing inside a shake or wag: only its first swing needs a wind-up
        majors.append(s)
    return majors, preps


def check_anticipation(tracks, fps, skip, prep_map, exempt):
    gap = max(2, round(0.1 * fps))
    events = {n: anticipation_events(xs, fps) for n, xs in tracks.items() if n not in skip}
    out = []
    for name, (majors, _) in events.items():
        if is_exempt(exempt, "anticipation", name):
            continue
        sources = {prefix(name)} | set(prep_map.get(prefix(name), []))
        preps = [p for n, (_, ps) in events.items() if prefix(n) in sources for p in ps]
        bare = [f for f in majors if not any(f - gap <= p <= f for p in preps)]
        if bare:
            out.append(finding("anticipation", WARN,
                               f"big move(s) at frame {', '.join(map(str, bare[:6]))} start cold. Start each with a "
                               "small opposite move (10-30% of the travel) in this part or the body that drives it.",
                               name))
    return out


def check_volume(group, tracks):
    vals = [tracks[t] for t in group]
    n = len(vals[0])
    worst, frame, active = 0.0, 0, 0
    for i in range(n):
        prod = 1.0
        for v in vals:
            prod *= v[i]
        if abs(prod - 1.0) > worst:
            worst, frame = abs(prod - 1.0), i
        if any(abs(v[i] - 1.0) > 0.03 for v in vals):
            active += 1
    label = "*".join(group)
    out = []
    if worst > 0.06:
        out.append(finding("volume", FAIL, f"volume off by {worst:.0%} at frame {frame}. Keep {label} near 1 "
                                           "(2D: sx = 1/sy, 3D: sx = sz = 1/sqrt(sy)).", label))
    if active / n > 0.6:
        out.append(finding("squash_overuse", WARN, f"squash or stretch is active on {active / n:.0%} of frames. "
                                                   "Use it on impacts and fast moves, not as a constant wobble.",
                           label))
    return out


def best_lag(a, b, max_lag, sign=1):
    """Lag (frames) of b behind a with the best velocity correlation, and that correlation."""
    va, vb = velocity(a), [sign * x for x in velocity(b)]
    best, best_lag_ = -2.0, 0
    for lag in range(0, max_lag + 1):
        xs, ys = va[: len(va) - lag], vb[lag:]
        m = min(len(xs), len(ys))
        if m < 4:
            break
        xs, ys = xs[:m], ys[:m]
        mx, my = sum(xs) / m, sum(ys) / m
        sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        sy = math.sqrt(sum((y - my) ** 2 for y in ys))
        if sx == 0 or sy == 0:
            continue
        r = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)
        if r > best:
            best, best_lag_ = r, lag
    return best_lag_, best


def check_chain(chain, tracks, fps):
    max_lag = max(4, round(0.5 * fps))
    min_lag = max(1, round(fps / 30))
    welded, judged = [], 0
    for a, b in zip(chain, chain[1:]):
        if track_range(tracks[a]) <= 1e-9 or track_range(tracks[b]) <= 1e-9:
            continue  # a still link: nothing to judge
        lag, r = best_lag(tracks[a], tracks[b], max_lag)
        if r < 0.5:
            continue  # the link does not follow its parent clearly enough to measure a lag
        judged += 1
        if lag < min_lag:
            welded.append(f"{a}->{b}")
    label = " -> ".join(chain)
    if not welded:
        return []
    level = FAIL if len(welded) == judged else WARN
    return [finding("overlap", level, f"{', '.join(welded)} move on the same frame. Drag each child {min_lag}+ "
                                      "frame(s) behind its parent (spring or phase offset).", label)]


def _turn(a, b, c):
    v1 = (b[0] - a[0], b[1] - a[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2))))


def check_arc(path, tracks, fps, contacts):
    xs, ys = tracks[path[0]], tracks[path[1]]
    pts = list(zip(xs, ys))
    steps = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    scale = max(track_range(xs), track_range(ys)) or 1.0
    eps = scale * 2e-3
    label = "/".join(path)
    out, i = [], 0
    min_steps = max(4, round(0.15 * fps))
    while i < len(steps):
        if steps[i] <= eps:
            i += 1
            continue
        j = i
        while j < len(steps) and steps[j] > eps:
            j += 1
        seg = pts[i:j + 1]
        big = 0.2 * max(steps[i:j])
        corners = [i + k for k in range(1, len(seg) - 1)
                   if _turn(seg[k - 1], seg[k], seg[k + 1]) > 0.6
                   and steps[i + k - 1] > big and steps[i + k] > big
                   and not any(abs(i + k - c) <= 2 for c in contacts)]
        if corners:
            out.append(finding("arcs", WARN, f"sharp corner at frame {', '.join(map(str, corners[:6]))}. Blend it "
                                             "into a curve, or list the frame in contacts if it is a contact.",
                               label))
        elif j - i >= min_steps:
            chord = math.dist(seg[0], seg[-1])
            if chord > 0.1 * scale:
                (x0, y0), (x1, y1) = seg[0], seg[-1]
                dev = max(abs((x1 - x0) * (y0 - y) - (x0 - x) * (y1 - y0)) / chord for x, y in seg)
                if dev / chord < 0.03:
                    out.append(finding("arcs", WARN, f"frames {i}-{j}: travels in a straight line. Organic motion "
                                                     "follows arcs.", label))
        i = j
    return out


def check_mirror(pair, tracks, fps):
    a, b = tracks[pair[0]], tracks[pair[1]]
    ra, rb = track_range(a), track_range(b)
    if ra <= 1e-9 or rb <= 1e-9 or abs(ra - rb) / max(ra, rb) >= 0.05:
        return []
    for sign in (1, -1):  # same axes, or mirrored axes with opposite signs
        lag1, r1 = best_lag(a, b, max(2, round(0.2 * fps)), sign)
        lag2, r2 = best_lag(b, a, max(2, round(0.2 * fps)), sign)
        if lag1 == 0 and lag2 == 0 and r1 > 0.98:
            return [finding("twins", WARN, f"{pair[0]} and {pair[1]} move identically. Offset one by 1-3 frames "
                                           "and vary its amplitude 10-20%.", "/".join(pair))]
    return []


def check_dead_holds(tracks, fps):
    names = list(tracks)
    n = len(tracks[names[0]])
    run = worst = 0
    for i in range(n - 1):
        if all(tracks[t][i + 1] == tracks[t][i] for t in names):
            run += 1
            worst = max(worst, run)
        else:
            run = 0
    if worst > 0.5 * fps:
        return [finding("dead_hold", WARN, f"every track is frozen for {worst} frames. Use a moving hold: 1-3% "
                                           "drift or a breath.")]
    return []


# ---------------------------------------------------------------- input

def is_exempt(exempt, check, track):
    names = exempt.get(check, [])
    return "*" in names or (track is not None and track in names)


def validate(doc):
    if not isinstance(doc, dict):
        raise BadInput("the file must hold a JSON object")
    fps = doc.get("fps", 24)
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or not math.isfinite(fps) or fps <= 0:
        raise BadInput("fps must be a positive number")
    context = doc.get("context", "character")
    if context not in CONTEXTS:
        raise BadInput(f"context must be one of {', '.join(CONTEXTS)}")
    dial = doc.get("dial", 1.0)
    if not isinstance(dial, (int, float)) or isinstance(dial, bool) or not math.isfinite(dial) or dial <= 0:
        raise BadInput("dial must be a positive number")
    tracks = doc.get("tracks")
    if not isinstance(tracks, dict) or not tracks:
        raise BadInput("tracks must be a non-empty object of name -> list of numbers")
    lengths = set()
    for k, v in tracks.items():
        if not isinstance(v, list) or len(v) < 3:
            raise BadInput(f"track {k} needs a list of at least 3 numbers")
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in v):
            raise BadInput(f"track {k} must hold only finite numbers")
        lengths.add(len(v))
    if len(lengths) != 1:
        raise BadInput("every track must have the same number of samples (one per frame)")

    def names_exist(key, item):
        for t in item:
            if t not in tracks:
                raise BadInput(f"{key} names a track that does not exist: {t}")

    for key, sizes in (("volume", (2, 3)), ("paths", (2,)), ("mirrors", (2,))):
        g = doc.get(key, [])
        if not isinstance(g, list) or any(not isinstance(it, list) or len(it) not in sizes for it in g):
            raise BadInput(f"each {key} entry must list {' or '.join(map(str, sizes))} track names")
        for it in g:
            names_exist(key, it)
    chains = doc.get("chains", [])
    if not isinstance(chains, list) or any(not isinstance(c, list) or len(c) < 2 for c in chains):
        raise BadInput("each chains entry must list at least 2 track names")
    for c in chains:
        names_exist("chains", c)
    contacts = doc.get("contacts", [])
    if not isinstance(contacts, list) or not all(isinstance(c, int) and not isinstance(c, bool) for c in contacts):
        raise BadInput("contacts must be a list of frame numbers")
    for key in ("prep", "exempt"):
        m = doc.get(key, {})
        if not isinstance(m, dict) or not all(isinstance(v, list) for v in m.values()):
            raise BadInput(f"{key} must map names to lists")
    return float(fps), context, float(dial)


def check_tracks(doc):
    fps, context, dial = validate(doc)
    tracks = {k: [float(x) for x in v] for k, v in doc["tracks"].items()}
    exempt = doc.get("exempt", {})
    scale = {t for g in doc.get("volume", []) for t in g}
    followers = {t for c in doc.get("chains", []) for t in c[1:]}
    out = []
    for name, xs in tracks.items():
        if name not in scale:
            out += check_ease(name, xs, fps)
        out += check_settle(name, xs, fps, context, dial)
    if context == "character":
        out += check_anticipation(tracks, fps, scale | followers, doc.get("prep", {}), exempt)
        out += check_dead_holds(tracks, fps)
    for g in doc.get("volume", []):
        out += check_volume(g, tracks)
    for c in doc.get("chains", []):
        out += check_chain(c, tracks, fps)
    for p in doc.get("paths", []):
        ptracks = tracks
        if doc.get("y_down"):
            ptracks = dict(tracks)
            ptracks[p[1]] = [-y for y in tracks[p[1]]]
        out += check_arc(p, ptracks, fps, doc.get("contacts", []))
    for m in doc.get("mirrors", []):
        out += check_mirror(m, tracks, fps)
    return [f for f in out if not is_exempt(exempt, f["check"], f["track"])]


# ---------------------------------------------------------------- easing curves

def bezier_report(x1, y1, x2, y2, samples=4000):
    for v in (x1, y1, x2, y2):
        if not math.isfinite(v):
            raise BadInput("control points must be finite numbers")
    if not (0 <= x1 <= 1 and 0 <= x2 <= 1):
        raise BadInput("x1 and x2 must be between 0 and 1 (CSS cubic-bezier rule)")

    def bez(t, p1, p2):
        u = 1 - t
        return 3 * u * u * t * p1 + 3 * u * t * t * p2 + t ** 3
    ts = [i / samples for i in range(samples + 1)]
    xs, ys = [bez(t, x1, x2) for t in ts], [bez(t, y1, y2) for t in ts]
    speeds = [(ys[i + 1] - ys[i]) / max(xs[i + 1] - xs[i], 1e-9) for i in range(samples)]
    peak_x = xs[max(range(samples), key=lambda i: speeds[i])]
    if abs(x1 - y1) < 1e-9 and abs(x2 - y2) < 1e-9:
        shape = "linear"
    else:
        shape = "ease-out (fast start)" if peak_x < 0.3 else "ease-in (slow start)" if peak_x > 0.7 else "ease-in-out"
    return {"overshoot": max(0.0, max(ys) - 1.0), "anticipation": max(0.0, -min(ys)),
            "peak_speed_at": peak_x, "shape": shape}


def spring_report(k, c, m=1.0):
    """Step response of m*x'' + c*x' + k*(x - 1) = 0 from x = 0, v = 0, solved exactly."""
    if not (math.isfinite(k) and k > 0 and math.isfinite(m) and m > 0 and math.isfinite(c) and c >= 0):
        raise BadInput("stiffness and mass must be positive, damping zero or more")
    w = math.sqrt(k / m)
    z = c / (2 * math.sqrt(k * m))
    if z < 1 - 1e-9:
        wd = w * math.sqrt(1 - z * z)
        overshoot = math.exp(-math.pi * z / math.sqrt(1 - z * z)) if z > 0 else 1.0

        def x(t):
            return 1 - math.exp(-z * w * t) * (math.cos(wd * t) + z * w / wd * math.sin(wd * t))
        rate = z * w
    elif z <= 1 + 1e-9:
        overshoot = 0.0

        def x(t):
            return 1 - (1 + w * t) * math.exp(-w * t)
        rate = w
    else:
        r1, r2 = -w * (z - math.sqrt(z * z - 1)), -w * (z + math.sqrt(z * z - 1))
        overshoot = 0.0

        def x(t):
            return 1 - (r2 * math.exp(r1 * t) - r1 * math.exp(r2 * t)) / (r2 - r1)
        rate = -r1
    if z == 0:
        settle, status = None, "never settles (no damping)"
    else:
        horizon = 14 / rate
        n = 40000
        last = 0.0
        for i in range(n + 1):
            t = horizon * i / n
            if abs(x(t) - 1) > 0.02:
                last = t
        settle, status = last, "settles"
    feel = ("never stops" if z == 0 else "bouncy" if z < 0.4 else "lively" if z < 0.7
            else "smooth, tiny overshoot" if z < 1 else "no overshoot")
    return {"damping_ratio": z, "natural_frequency_hz": w / (2 * math.pi), "overshoot": overshoot,
            "settle_seconds_2pct": settle, "status": status, "feel": feel}


def rounded(d):
    return {k: round(v, 4) if isinstance(v, float) else v for k, v in d.items()}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    t = sub.add_parser("tracks", help="check a track file")
    t.add_argument("file")
    t.add_argument("--json", action="store_true", help='print {"ok": bool, "findings": [...]}')
    b = sub.add_parser("bezier", help="report a cubic-bezier easing")
    b.add_argument("curve", help='"x1,y1,x2,y2" or "cubic-bezier(x1,y1,x2,y2)"')
    s = sub.add_parser("spring", help="report a damped spring")
    s.add_argument("--stiffness", type=float, required=True)
    s.add_argument("--damping", type=float, required=True)
    s.add_argument("--mass", type=float, default=1.0)
    a = p.parse_args(argv)
    try:
        if a.mode == "bezier":
            nums = a.curve.replace("cubic-bezier", "").strip("() ").split(",")
            if len(nums) != 4:
                raise BadInput("give exactly four numbers: x1,y1,x2,y2")
            print(json.dumps(rounded(bezier_report(*[float(x) for x in nums]))))
            return 0
        if a.mode == "spring":
            print(json.dumps(rounded(spring_report(a.stiffness, a.damping, a.mass))))
            return 0
        with open(a.file) as fh:
            doc = json.load(fh)
        results = check_tracks(doc)
    except (OSError, ValueError) as exc:  # BadInput and json.JSONDecodeError are ValueErrors
        print(f"bad input: {exc}", file=sys.stderr)
        return 2
    fails = [r for r in results if r["level"] == FAIL]
    if a.json:
        print(json.dumps({"ok": not fails, "findings": results}, indent=2))
    else:
        for r in results:
            where = f" [{r['track']}]" if r["track"] else ""
            print(f"{r['level']} {r['check']}{where}: {r['msg']}")
        print(f"{'PASS' if not fails else 'FAIL'}: {len(fails)} fail, {sum(r['level'] == WARN for r in results)} warn")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
