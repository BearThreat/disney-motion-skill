---
name: disney-motion
description: Makes code-driven animation feel alive and appealing by turning Disney's 12 animation principles into numbers, code operators and a motion checker. Use when you write, tune or fix motion - character, creature, object, procedural or game animation, UI transitions and micro-interactions, easing curves, springs and animation timing - in Three.js, canvas, SVG, Lottie, Remotion, GSAP, CSS or Framer Motion, especially when it must feel weighty, cartoony or "Disney/Pixar-like", or looks stiff, robotic, floaty or too bouncy. Not for static design or video editing.
---

# Disney Motion

Agents usually apply the 12 principles as decoration. Everything wobbles, every part moves on the same frame, every move runs at one speed, and nothing holds still long enough to read. Disney animators used the principles for acting: the audience sees the thought, then the action, then the reaction. This skill turns each principle into a number and a code operator. It also gives a checker that measures the result.

## Contract

- **Input:** what moves, why it moves (intent or emotion), the medium and stack, and the frame rate.
- **Output:** animation code with (1) a beat-sheet comment at the top, (2) named timing and amplitude constants (no magic numbers in the tween calls), and (3) a `scripts/motion_check.py` result with 0 FAIL for the chosen context.
- **Not included:** modelling, rigging, rendering pipelines, art direction. For UI micro-interactions, this skill sets the motion only and does not choose what to animate.

## Workflow

1. **Write the beat sheet first.** One line per beat, with its frames at 24 fps (or its milliseconds for UI). The beats depend on what moves:
   - **Character:** *thought* (what it wants) → *anticipation* → *action* → *follow-through / settle* → *hold*. If you cannot say what the character thinks, the motion will not read. Example: the top of `disney()` in `examples/hop_demo.py`.
   - **Object or prop:** *force or purpose* → *wind-up, only if it explains the action* → *action* → *settle*.
   - **UI:** *trigger* → *immediate feedback* (no wind-up before the response to a user's input) → *transition* → *stable state*.
2. **Pick the dial.** It scales amplitudes: squash, overshoot, anticipation depth and lag. It does not scale durations; mass and size set those.

   | Context | Dial | Feel |
   |---|---|---|
   | Product UI, dashboards | 0.15-0.3 | Quick and calm. Overshoot 5% or less (3% on modals), no squash on text. |
   | Explainers, onboarding, marketing | 0.4-0.6 | Friendly. Light squash on shapes, small overshoot. |
   | Game or film character, realistic | 0.6-1.0 | Weight and timing first. Squash mostly in flesh, tails and ears. |
   | Cartoon character | 1.0-1.5 | Big poses, snappy timing, clear stretch. |

3. **Block poses, then timing.** Key poses first, each with a clear silhouette. Then set the frames per beat. Then add breakdowns that favour one key (uneven spacing). Use pose-to-pose for acting beats and straight-ahead (physics or springs) for appendages. Most procedural rigs need both.
4. **Apply the operators.** See the table below. Drive the motion from the root (hips or body). Make children lag behind their parents. Stage one main action at a time.
5. **Check, then watch.** Sample every animated channel once per frame and write the samples to JSON. `examples/tracks.example.json` is a file you can copy. `SKILL_DIR` below is the folder that holds this `SKILL.md`. Run:
   `python3 "$SKILL_DIR/scripts/motion_check.py" tracks path/to/tracks.json`
   Fix each FAIL. If the motion is intended (ballistic flight, a machine, a deliberate wag), add it to `exempt` and write the reason in the beat sheet. Treat each WARN as a question: "is this intentional?" For an easing curve or a spring, run `python3 "$SKILL_DIR/scripts/motion_check.py" bezier "0.2,0,0,1"` or `... spring --stiffness 170 --damping 26`. The checker's docstring lists every check, every optional field (`beats`, `exempt`, `wind_ups`, `contacts`) and its sampling limits.
   The checker is a diagnostic for the samples you give it. It does not judge appeal. Always watch the final motion at its real frame rate (a GIF, a video or a live preview). Use a 6-8 frame contact sheet to compare poses.

## Principles as operators (defaults at dial 1.0, 24 fps)

| Principle | Operator | Default numbers |
|---|---|---|
| Squash and stretch | Scale along the velocity or impact axis, and keep the volume | 2D: `sx = 1/sy`. 3D: `sx = sz = 1/sqrt(sy)`. Impact squash 0.7-0.8. Stretch 1.15-1.3, scaled by speed. Rest at 1.0. |
| Anticipation | A small move opposite to the main move | 10-30% of the travel. Lasts 0.5-2× the action time. Faster actions need more anticipation. |
| Staging | One focal action. Other parts hold or quiet down | Secondary parts run at ≤ 30% amplitude during the main beat. Clear silhouette. |
| Straight-ahead / pose-to-pose | Keys for acting. Simulation or springs for appendages | Body = keys. Tail, ears, hair, cloth = springs. |
| Follow-through / overlap | Children lag their parent. Loose parts overshoot and settle | Each link lags 1-3 frames (24 fps). Spring damping ratio ζ 0.3-0.6: each swing is 10-37% of the one before. |
| Slow in / slow out | Ease into and out of key poses | Not linear, except for machines. Use ease-out for reactions and entrances, ease-in for falls. |
| Arcs | Rotate about pivots or use curved paths, not straight lerps | Heads, hands and jumps travel in arcs. Sharp corners only at contact. |
| Secondary action | A smaller action that supports the main one | Breath, blink, tail flick, flung particles. It must not compete. |
| Timing | Frames per beat set weight and mood | A light object settles in 4-8 frames, a heavy one in 12-24. Hold a pose 6-12 frames so it reads. |
| Exaggeration | Push the key poses, not every frame | Push 20-50% past realistic at the keys, then return to normal. |
| Solid drawing | Keep volume and weight. Avoid twins | Offset left and right limbs by 1-3 frames and vary their amplitude 10-20%. |
| Appeal | Clarity, asymmetry, variation | Live idles vary each cycle by ±5-10%; exported loops stay seamless. Moving holds drift by 1-3%. |

Code recipes for these operators, per stack and for procedural rigs: `references/recipes.md`. Load it only when you write the code. UI-specific numbers (durations, springs, reduced motion): `references/ui.md`.

## Failure modes to catch (the checker finds most of them)

- **Robot:** constant speed across a move (`ease` FAIL).
- **Blob:** squash that changes the volume (`volume` FAIL), or squash on every frame (`squash_overuse`).
- **Welded parts:** the tail, ears or hair rotate with the body on the same frame (`overlap` FAIL).
- **Jelly:** swings that barely shrink, or more than 2 wobbles on UI (`jelly`).
- **Pop:** a big move with no wind-up (`anticipation`).
- **Ruler:** straight paths and sharp corners in mid-air (`arcs`).
- **Statue:** a full freeze longer than 0.5 s (`dead_hold`). Use a moving hold.
- **Noise:** secondary motion as large as the main action. Every principle on every element at once.

## Edge cases

- **Reduced motion:** honour `prefers-reduced-motion` or the platform setting. Keep fades and drop travel, squash and overshoot.
- **Frame rate:** author in seconds, not frames. Convert the frame numbers in this skill with `seconds = frames / 24`. At 60 fps, lags are 2-8 frames.
- **"On twos" look:** hold each pose 2 frames (steps at 12 fps) for a hand-drawn feel. Check the smooth curves first, then apply the steps and watch the stepped result at full speed.
- **Physics already drives it:** keep the physics. Add anticipation and squash on top, and do not keyframe over it.
- **Text and icons:** never squash readable text. Use opacity, a small translate (4-16 px) or a scale between 0.96 and 1.
- **Loops:** idles loop over 2-4 s with a cycle that is not uniform. Offset the phase of each part.

Setup, install and removal for each agent: `references/setup.md`.
