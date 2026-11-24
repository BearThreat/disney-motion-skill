# Setup

The skill is one folder: `SKILL.md`, `references/`, `scripts/`, `examples/` and `tests/`. Keep the whole folder together, because `SKILL.md` points to the other files by relative path. The checker uses only the Python 3.9+ standard library. The GIF render in the example also needs Pillow.

## Install

Agents load only the skill's name and description at startup. The body and references load only when a task matches, so the skill uses almost no context until it is needed.

| Agent | Command |
|---|---|
| Claude Code (all projects) | `git clone https://github.com/BearThreat/disney-motion-skill ~/.claude/skills/disney-motion` |
| Claude Code (one project) | `git clone https://github.com/BearThreat/disney-motion-skill .claude/skills/disney-motion` |
| Codex and agents that read `~/.agents/skills` | `git clone https://github.com/BearThreat/disney-motion-skill ~/.agents/skills/disney-motion` |
| `skills` CLI (Node.js 22.20+) | `npx skills add BearThreat/disney-motion-skill` (add `-g` for all projects) |
| Other agents | Copy the whole folder to where your agent reads skills, or give it the repository link and ask it to follow `SKILL.md`. |

## Check that it works

Run these in the folder you installed (for example `~/.claude/skills/disney-motion`):

```bash
cd ~/.claude/skills/disney-motion
python3 examples/hop_demo.py
python3 scripts/motion_check.py tracks examples/out/naive.tracks.json    # exit 1: several FAIL
python3 scripts/motion_check.py tracks examples/out/disney.tracks.json   # exit 0: no findings
python3 -m unittest discover -s tests
```

## Update and remove

- Git clone: run `git pull` in the folder you cloned (for example `git -C ~/.agents/skills/disney-motion pull`). Delete that folder to remove.
- `skills` CLI: `npx skills update disney-motion` to update, `npx skills remove disney-motion` to remove.

## Troubleshooting

- **The skill does not trigger.** Ask for it by name ("use the disney-motion skill"). Check that the folder holds `SKILL.md` at its top level.
- **`motion_check.py` prints `bad input` and exits 2.** Every track needs the same number of finite numbers (at least 3). Names in `volume`, `chains`, `paths` and `mirrors` must exist in `tracks`. Copy `examples/tracks.example.json` as a start.
- **A move is meant to be linear** (a thrown ball in flight, a machine). Add it to `exempt`, for example `"exempt": {"ease": ["ball.x"]}`.
