#!/usr/bin/env python3
"""Hop, land, shake off: the same creature animated two ways.

  naive  - what code animation usually looks like: linear tweens, a rigid tail,
           a constant squash wobble that changes the creature's volume, a dead hold.
  disney - the recipes in this skill: a beat sheet, anticipation, an arc,
           squash and stretch with volume kept, a spring-chain tail, a decaying shake,
           and a moving hold.

Writes examples/out/{naive,disney}.tracks.json for scripts/motion_check.py.
With --gif PATH (needs Pillow) it also renders a side-by-side GIF.

    python3 examples/hop_demo.py
    python3 scripts/motion_check.py tracks examples/out/disney.tracks.json
    uv run --with pillow python examples/hop_demo.py --gif assets/hop.gif
"""
from __future__ import annotations

import argparse
import json
import math
import os

FPS = 24
FRAMES = 104
TAIL = 4  # tail links


def smooth(t):  # ease-in-out, 0..1
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def ease_in(t):
    t = max(0.0, min(1.0, t))
    return t * t


def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------- naive
# body.y is the height of the body's centre above the ground: feet lift + half the body height * sy.
HALF_H = 20.0


def naive():
    tr = {k: [] for k in ["body.x", "body.y", "body.rot", "body.sx", "body.sy", "head.rot"]
          + [f"tail{i}.rot" for i in range(1, TAIL + 1)]}
    for f in range(FRAMES):
        x = lift = rot = 0.0
        if 12 <= f <= 40:  # linear hop: straight up, straight down
            t = (f - 12) / 28
            x = 160 * t
            lift = 90 * (t * 2 if t < 0.5 else (1 - t) * 2)
        elif f > 40:
            x = 160
        if 52 <= f <= 76:  # shake at constant amplitude, stops dead
            rot = 14 * math.sin((f - 52) / 24 * 4 * 2 * math.pi)
        sy = 1 + 0.08 * math.sin(f * 0.5)  # always wobbling, and the width never compensates
        tr["body.x"].append(x)
        tr["body.y"].append(lift + HALF_H * sy)
        tr["body.rot"].append(rot)
        tr["body.sx"].append(1.0)
        tr["body.sy"].append(sy)
        tr["head.rot"].append(rot)
        for i in range(1, TAIL + 1):
            tr[f"tail{i}.rot"].append(rot + 35)  # rigid: welded to the body
    return tr


# ---------------------------------------------------------------- disney
# Beat sheet (24 fps)
#   0-12  moving hold: breathing, ready                        thought: "I can make that"
#  12-22  anticipation: a small nod, then crouch to sy 0.70 and lean back
#  22     takeoff (contact): crouch unwinds into stretch over 2 frames
#  22-40  action: parabolic arc, 160 px forward and 90 px up; horizontal speed builds during
#         takeoff, then stays constant in the air; stretch follows vertical speed
#  40     touchdown (contact): squash 0.72 on the contact frame
#  40-52  landing: squash springs back with a small overshoot; a short skid uses up the speed
#  52-80  secondary beat: shake off; head leads the body; the wave runs down the tail and decays
#  80-104 moving hold: breath, head toss, the tail settles on its springs
TAKEOFF, TOUCHDOWN, AIR_A = 22, 40, 0.15


def disney():
    tr = {k: [] for k in ["body.x", "body.y", "body.rot", "body.sx", "body.sy", "head.rot"]
          + [f"tail{i}.rot" for i in range(1, TAIL + 1)]}
    air = TOUCHDOWN - TAKEOFF
    v_air = 160 / (1 - AIR_A / 2)  # horizontal speed in the air; the takeoff ramp meets it exactly
    ang = [35.0] * (TAIL + 1)  # tail spring chain state, angles in degrees
    vel = [0.0] * (TAIL + 1)
    prev_y = prev_vy = 0.0
    for f in range(FRAMES):
        x = lift = rot = head = 0.0
        sy = 1.0
        if 12 <= f < TAKEOFF:  # anticipation
            t = smooth((f - 12) / 10)
            sy = 1 - 0.30 * t
            rot = -8 * t + 3 * math.sin(math.pi * min(1.0, (f - 12) / 4))  # a tiny nod forward first
        elif TAKEOFF <= f < TOUCHDOWN:  # airborne
            t = (f - TAKEOFF) / air
            x = v_air * t * t / (2 * AIR_A) if t < AIR_A else v_air * (t - AIR_A / 2)
            lift = 360 * t * (1 - t)  # parabola, apex 90 px
            stretch = 1 + 0.22 * min(1.0, abs(20 * (1 - 2 * t)) / 20)
            sy = lerp(0.70, stretch, min(1.0, (f - TAKEOFF) / 2))
            rot = -8 * (1 - smooth(t / 0.3)) + 10 * (2 * t - 1) * smooth(t / 0.3)  # nose follows the arc
        elif f >= TOUCHDOWN:
            tau = 2.5  # skid: the air speed decays over a few frames
            x = 160 + v_air / air * tau * (1 - math.exp(-(f - TOUCHDOWN) / tau))
            t = (f - TOUCHDOWN) / 12
            sy = 1 - 0.28 * math.exp(-5 * t) * math.cos(2.2 * math.pi * t)  # 0.72 on the contact frame
            rot = 10 * math.exp(-6 * t)
        if f >= 52:  # shake off: decaying wave, head leads the body
            t = (f - 52) / FPS
            env = math.exp(-t / 0.45) * smooth(t / 0.12)
            rot += 13 * env * math.sin(2 * math.pi * 4 * t)
            head = 16 * env * math.sin(2 * math.pi * 4 * t + 0.9)
        if f >= 80:  # head toss into the moving hold
            t = (f - 80) / 24
            head += 4 * math.sin(math.pi * min(1.0, t * 2)) * (1 - t)
        if f < 12 or f > 56:
            sy += 0.012 * math.sin(2 * math.pi * f / 40)  # breath
        sx = 1 / sy  # 2D: keep the area
        y = lift + HALF_H * sy
        # tail: each link springs toward its parent; the body's vertical motion kicks the base
        vy_body = y - prev_y
        ay_body = vy_body - prev_vy
        prev_y, prev_vy = y, vy_body
        ang[0] = rot
        sub = 4
        for _ in range(sub):
            for i in range(1, TAIL + 1):
                target = ang[i - 1] + (35 if i == 1 else 6)
                if i == 1:
                    target += 2.5 * vy_body - 4 * ay_body
                k, c = 90.0 * 0.85 ** (i - 1), 7.0 * 0.92 ** (i - 1)  # softer toward the tip
                vel[i] += (k * (target - ang[i]) - c * vel[i]) / (FPS * sub)
                ang[i] += vel[i] / (FPS * sub)
        tr["body.x"].append(x)
        tr["body.y"].append(y)
        tr["body.rot"].append(rot)
        tr["body.sx"].append(sx)
        tr["body.sy"].append(sy)
        tr["head.rot"].append(head + rot)
        for i in range(1, TAIL + 1):
            tr[f"tail{i}.rot"].append(ang[i])
    return tr


def doc(tracks):
    return {
        "fps": FPS, "context": "character", "dial": 1.0, "tracks": tracks,
        "volume": [["body.sx", "body.sy"]],
        "chains": [["body.rot"] + [f"tail{i}.rot" for i in range(1, TAIL + 1)]],
        "paths": [["body.x", "body.y"]],
        "contacts": [TAKEOFF, TOUCHDOWN],
        "prep": {"head": ["body"]},
    }


# ---------------------------------------------------------------- render
def ellipse(cx, cy, rx, ry, rot_deg, n=40):
    r = math.radians(rot_deg)
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        px, py = rx * math.cos(a), ry * math.sin(a)
        pts.append((cx + px * math.cos(r) - py * math.sin(r), cy + px * math.sin(r) + py * math.cos(r)))
    return pts


def draw_creature(d, tr, f, ox, ground):
    W, H = 64, 40
    sx, sy, rot = tr["body.sx"][f], tr["body.sy"][f], tr["body.rot"][f]
    rw, rh = W / 2 * sx, H / 2 * sy
    x, cy = ox + tr["body.x"][f], ground - tr["body.y"][f]  # body.y is the centre height
    lift = tr["body.y"][f] - rh
    # shadow shrinks with height (staging: reads the jump)
    s = max(0.35, 1 - lift / 140)
    d.ellipse([x - 34 * s, ground - 4 * s, x + 34 * s, ground + 4 * s], fill=(205, 194, 172))
    orange, dark, cream = (226, 112, 44), (92, 46, 30), (250, 238, 220)
    # tail from the rear, screen y down so angles flip
    r = math.radians(-rot)
    bx = x - rw * 0.85 * math.cos(r)
    by = cy - rw * 0.85 * math.sin(r) * -1
    px, py = bx, by
    for i in range(1, TAIL + 1):
        a = math.radians(180 - tr[f"tail{i}.rot"][f])
        nx, ny = px + 15 * math.cos(a), py - 15 * math.sin(a)
        w = 17 - 3 * i
        col = cream if i == TAIL else orange
        d.line([px, py, nx, ny], fill=col, width=max(3, w))
        d.ellipse([nx - w / 2, ny - w / 2, nx + w / 2, ny + w / 2], fill=col)
        px, py = nx, ny
    d.polygon(ellipse(x, cy, rw, rh, -rot), fill=orange)
    # head at the front top
    hr = math.radians(-rot)
    hx = x + rw * 0.8 * math.cos(hr) + rh * 0.6 * math.sin(hr)
    hy = cy + rw * 0.8 * math.sin(hr) - rh * 0.6 * math.cos(hr)
    head = -tr["head.rot"][f]
    d.polygon(ellipse(hx, hy, 17, 14, head), fill=orange)
    a = math.radians(head)
    for ear in (-0.5, 0.35):  # ears
        ex, ey = hx + 10 * math.sin(a + ear), hy - 12 * math.cos(a + ear)
        d.polygon([(ex - 5, ey + 4), (ex + 5, ey + 4), (ex + 1, ey - 9)], fill=dark)
    sx2, sy2 = hx + 15 * math.cos(a), hy + 15 * math.sin(a)
    d.ellipse([sx2 - 4, sy2 - 3, sx2 + 4, sy2 + 3], fill=dark)  # nose
    ex, ey = hx + 6 * math.cos(a) - 4 * math.sin(a), hy + 6 * math.sin(a) - 4 * math.cos(a) * -1 - 6
    d.ellipse([ex - 2, ey - 2, ex + 2, ey + 2], fill=dark)


def render_gif(a, b, path):
    from PIL import Image, ImageDraw, ImageFont
    PW, PH = 400, 230
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    frames = []
    for f in range(FRAMES):
        im = Image.new("RGB", (PW, PH * 2 + 4), (244, 239, 228))
        d = ImageDraw.Draw(im)
        for row, (tr, label) in enumerate([(a, "naive tween"), (b, "disney-motion skill")]):
            top = row * (PH + 4)
            ground = top + PH - 34
            d.line([0, ground, PW, ground], fill=(200, 190, 170), width=2)
            draw_creature(d, tr, f, 90, ground)
            d.rounded_rectangle([10, top + 10, 20 + d.textlength(label, font=font), top + 36], 6,
                                fill=(255, 252, 245))
            d.text((15, top + 13), label, fill=(40, 40, 60), font=font)
        d.rectangle([0, PH, PW, PH + 4], fill=(90, 90, 110))
        frames.append(im)
    # loop without a jump cut: fade the creatures out at the end and in at the start
    blank = frames[0].copy()
    bd = ImageDraw.Draw(blank)
    for row in range(2):
        top = row * (PH + 4)
        bd.rectangle([0, top + 40, PW, top + PH - 1], fill=(244, 239, 228))
        bd.line([0, top + PH - 34, PW, top + PH - 34], fill=(200, 190, 170), width=2)
    fade_in, fade_out = 4, 8
    for k in range(fade_in):
        frames[k] = Image.blend(blank, frames[k], (k + 1) / (fade_in + 1))
    frames += [Image.blend(frames[-1], blank, (k + 1) / fade_out) for k in range(fade_out)]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0,
                   optimize=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "out"))
    p.add_argument("--gif")
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    n, s = naive(), disney()
    for name, tr in (("naive", n), ("disney", s)):
        with open(os.path.join(a.out, f"{name}.tracks.json"), "w") as fh:
            json.dump(doc(tr), fh)
    if a.gif:
        render_gif(n, s, a.gif)
    print(f"wrote {a.out}/naive.tracks.json and disney.tracks.json" + (f" and {a.gif}" if a.gif else ""))


if __name__ == "__main__":
    main()
