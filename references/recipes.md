# Recipes

Load this only when you write the animation code. Every recipe works in seconds (`dt`), so it works at any frame rate. The working version of all of them together is `examples/hop_demo.py` (`disney()`).

## 1. Damped spring (follow-through, overlap, settle)

Use one spring per loose part. It gives lag, overshoot and decay from three numbers.

```js
// state: { x, v } ; zeta = c / (2*sqrt(k*m))
// zeta 0.3-0.6 = lively (each swing is 37-10% of the last), 0.7-0.9 = calm, 1.0 = no overshoot
function springStep(s, target, k, c, dt, m = 1) {
  const wn = Math.sqrt(k / m);                       // natural frequency, rad/s
  const n = Math.max(1, Math.ceil(dt * wn / 0.1));   // substeps keep semi-implicit Euler stable
  const h = dt / n;
  for (let i = 0; i < n; i++) {
    const a = (k * (target - s.x) - c * s.v) / m;
    s.v += a * h;
    s.x += s.v * h;
  }
  return s.x;
}
```

How to pick k and c: choose the undamped natural frequency `f` (Hz) and ratio `zeta`. Then `k = (2*PI*f)^2 * m` and `c = 2*zeta*sqrt(k*m)`. The visible wobble is a little slower than `f`: `f * sqrt(1 - zeta^2)`. A tail or ear on a small creature: f ≈ 2-3 Hz, zeta ≈ 0.35. A heavy coat or belly: f ≈ 1-1.5 Hz, zeta ≈ 0.5. Check a pair with `motion_check.py spring --stiffness K --damping C`. It reports the overshoot and the 2% settle time.

The ratio between one swing and the next (on opposite sides) is `exp(-PI*zeta / sqrt(1 - zeta^2))`. The number of visible swings also depends on how hard the part is pushed and on the size at which a swing stops being visible.

## 2. Chain overlap (tails, hair, antennae, ears, cloth strips)

```js
// links[0] is the root. Its x is set from the body every frame. Each child springs toward
// its parent's angle plus its rest offset. Angles in degrees.
const links = [{ x: 0, v: 0 }, ...Array.from({ length: 4 }, (_, i) => ({ x: 0, v: 0, rest: i ? 6 : 35 }))];

function updateChain(bodyAngle, bodyKick, dt) {
  links[0].x = bodyAngle;
  for (let i = 1; i < links.length; i++) {
    const k = 90 * 0.85 ** (i - 1);                  // softer toward the tip: the wave travels outward
    const c = 2 * 0.37 * Math.sqrt(k);               // zeta 0.37
    const target = links[i - 1].x + links[i].rest + (i === 1 ? bodyKick : 0);
    springStep(links[i], target, k, c, dt);
  }
}
```
`bodyKick` turns body velocity or acceleration into a swing (for example `2.5*vy - 4*ay`), so a jump makes the tail whip.

## 3. Squash and stretch, volume kept

```js
const stretch = 1 + amount * clamp(speed / speedForMax, 0, 1);   // along the velocity
const sy = impact ? 1 - squashDepth : stretch;                     // squash on contact
const sx = 1 / sy;                // 2D area kept
// 3D: sx = sz = 1 / Math.sqrt(sy)
// rotate the scale axis to the velocity direction, and keep the contact point on the ground:
// pivot at the feet, or offset y by (1 - sy) * halfHeight
```
Squash for 2-4 frames on impact, then spring back to 1 (recipe 1, zeta ≈ 0.4). A rest pose is always 1.0.

## 4. Anticipation

```js
// D = main travel, p = prep fraction (0.1-0.3), times in seconds; t is time since the beat began
function anticipate(t, D, p, tPrep, tAction) {
  if (t < tPrep) return -p * D * easeInOut(t / tPrep);
  const u = Math.min(1, (t - tPrep) / tAction);      // clamp: holds at D after the beat
  return -p * D + (D + p * D) * easeOut(u);
}
```
For a jump, crouch (squash 0.7-0.85 and lower the body), lean back, and dip the head a little. A fast action needs a longer or deeper wind-up. A small action needs almost none. Never put a wind-up before the response to a user's click or tap: it reads as lag.

## 5. Arcs

- Rotate limbs and heads about their pivot. Do not lerp their positions.
- For a jump, use a parabola: `y = h * 4 * t * (1 - t)`. Make horizontal speed constant in the air, and ease only the takeoff and landing.
- For a screen-space move from A to B, use a quadratic Bézier with the control point offset perpendicular to the path by 10-25% of its length.

## 6. Moving hold, breath, idle

```js
const breath = 0.012 * Math.sin(2 * Math.PI * t / 3.2);      // 1-2% scale, period 2.5-4 s
const drift = 0.8 * noise1D(t * 0.4);                          // degrees, slow
```
Never let a character freeze completely for more than 0.5 s. Blink every 2-6 s at random intervals. A blink takes 3-4 frames to close and 4-6 to open.

## 7. Decaying shake or wag

```js
const env = Math.exp(-t / tau) * smoothstep(0, 0.12, t);   // tau 0.3-0.6 s
angle = A * env * Math.sin(2 * Math.PI * freq * t + phase); // freq 3-5 Hz for a shake-off
// head leads the body: head phase +0.5..1.0 rad, tail driven by recipe 2
```

## 8. Variation (appeal)

- Twins: offset mirrored parts by 1-3 frames and scale one by 0.85-0.95.
- Loops: add ±5-10% noise to amplitude and period per cycle. Do not sync parts on one master phase.
- Pose asymmetry: tilt the head 5-15°, put weight on one leg, rotate the shoulders against the hips.

## Stack notes

- **Three.js / Babylon / game engines:** run recipes 1-2 in the update loop with real `dt` and clamp `dt` to ≤ 1/30. Apply squash on a parent "squash" node whose pivot sits at the contact point, so the rig's bones are not scaled.
- **GSAP:** use timelines with labels, one label per beat. Use `power2.out` for actions, `back.out(1.4)` (about 7% overshoot) for explainer or character overshoot, `back.out(1.0)` or less for product UI, and `elastic.out(1, 0.4)` only for a cartoon dial of 1.0 or more. Add overlap with position offsets (`"<0.04"`).
- **Framer Motion / Motion:** `transition={{ type: "spring", stiffness, damping, mass }}`. Stagger children by 30-60 ms.
- **CSS:** `cubic-bezier()` for single eases. Use `linear()` with sampled points for springs (generate the points from recipe 1). Use `@keyframes` with a squash keyframe for impacts.
- **Remotion:** use `spring({ frame, fps, config: { damping, stiffness, mass } })` and `interpolate()` per beat. Remotion always renders at its own fps, so author the beats in seconds.
- **Lottie / After Effects:** add an overshoot keyframe and set ease influence to 60-85%. Most Lottie players do not run After Effects expressions, so bake expressions and rig chains to plain keyframes before export, then check the result in the target player.
- **Python / Blender:** set the F-Curve interpolation to BEZIER with AUTO_CLAMPED handles for keys. Bake springs from recipe 1 on frame-change handlers.
