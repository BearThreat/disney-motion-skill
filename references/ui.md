# UI motion numbers

Load this only for product UI, web or app interface motion. Interfaces use the same principles at a dial of 0.15-0.3: motion must explain a change in state, and it must not slow the user down.

Overshoot targets: 5% or less for most UI, 3% or less for modals and sheets, none on text. The checker fails UI overshoot above 10%; that is a hard limit, not the target. Measured peaks: CSS `cubic-bezier(0.34, 1.56, 0.64, 1)` ≈ 10% (too much for product UI); GSAP `back.out(1.2)` ≈ 5.3%, `back.out(1.0)` ≈ 3.7%, `back.out(0.8)` ≈ 2.3%.

| Element | Duration | Easing / spring |
|---|---|---|
| Hover, press feedback | 80-150 ms | ease-out; press scale 0.96-0.98 |
| Small toggle, checkbox, chip | 150-200 ms | `cubic-bezier(0.2, 0, 0, 1)` or spring k 400-600, ζ 0.7-0.85 |
| Dropdown, popover, tooltip enter | 150-250 ms | ease-out; scale 0.95→1 from the trigger's origin |
| The same, on exit | 100-150 ms | ease-in; about 2/3 of the enter time |
| Modal, sheet, drawer | 250-350 ms | ease-out or spring ζ 0.8-0.9; a small overshoot (≤ 3%) is fine on mobile sheets |
| Page / route transition | 250-400 ms | ease-in-out; shared-element moves follow an arc |
| List stagger | 30-60 ms per item | cap the total stagger at about 300 ms |

How each principle applies in UI:

- **Anticipation:** a press-down state (scale 0.97) before a release. Never add a wind-up before the response to a user action: it reads as lag.
- **Follow-through:** the children of a panel arrive 30-60 ms after the panel. The content settles after its container.
- **Squash and stretch:** only on non-text shapes (a FAB, a toggle knob, a drag handle). At most 5-10%.
- **Arcs:** a shared element that moves diagonally travels on a slight curve, not a straight line.
- **Staging:** animate only the element that changed and its direct context. Do not move anything else.
- **Timing:** larger elements and longer distances take more time, but never more than 500 ms for any interaction.

Accessibility: honour `prefers-reduced-motion: reduce`. Replace travel and scale with a 150 ms opacity fade, and remove overshoot, parallax and looping motion. WCAG 2.2 SC 2.2.2 (Pause, Stop, Hide): moving content that starts by itself, lasts more than 5 seconds and runs next to other content needs a way to pause, stop or hide it, unless the motion is essential. This applies to one-shot motion as well as loops.

Check a curve: `python3 scripts/motion_check.py bezier "0.2,0,0,1"` (no overshoot) or `"0.34,1.56,0.64,1"` (about 10%). `motion_check.py tracks` with `"context": "ui"` fails overshoot above 10% and warns on more than 2 wobbles.
