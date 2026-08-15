#!/usr/bin/env python3
"""ORBITAL DEFENSE — the playable board on the profile README.

A visitor flies the interceptor; hostile packets fall from orbit and the
interceptor shoots them down before one reaches the surface. GitHub READMEs
cannot run scripts, so every command arrives as an issue: three links on the
board (left / fire / right) each open a pre-filled issue, a workflow feeds the
title to this script, and the rendered board is committed back.

Difficulty escalates with survival time (spawn rate ramps up per turn), so
this isn't a puzzle with a solved answer — it's a score to beat, seeded per
run so each attempt is reproducible from its own state but not predictable in
advance.

Usage:
    engine.py move <left|right|fire> [--actor <login>]   apply a command, reply
    engine.py new                                        launch a fresh run
    engine.py render                                     re-render the README block only
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
import urllib.parse

REPO = "Divyansh2602/Divyansh2602"

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "game" / "state.json"
README_PATH = ROOT / "README.md"

BLOCK_START = "<!-- INTRUSION-GRID:START -->"
BLOCK_END = "<!-- INTRUSION-GRID:END -->"

COLS = 5
ROWS = 6  # rows 0..ROWS-2 are airspace; ROWS-1 is the surface / interceptor lane
# Each move round-trips through a GitHub issue (~1 min), so a hostile needs
# real travel time: ROWS-1 turns from spawn to breach, giving a player who
# never reacts several fire attempts before anything is actually lethal.

ACTIONS = ("left", "right", "fire")
ACTION_LABEL = {"left": "steer left", "right": "steer right", "fire": "fire"}


# ── state ────────────────────────────────────────────────────────────────────

def new_seed() -> int:
    return random.SystemRandom().randrange(1, 2**31 - 1)


def rng_for(seed: int, turn: int) -> random.Random:
    """A fresh, deterministic generator for one turn's spawn roll. Reproducible
    from (seed, turn) alone, so no RNG internal state needs to be persisted."""
    return random.Random((seed * 1_000_003) ^ turn)


def fresh_state(stats: dict) -> dict:
    state = {
        "rocket_col": COLS // 2,
        "enemies": [],
        "score": 0,
        "turn": 0,
        "seed": new_seed(),
        "status": "active",       # active | breached
        "last_action": None,
        "last_actor": None,
        "stats": stats,
    }
    r = rng_for(state["seed"], 0)
    state["enemies"].append({"col": r.randrange(COLS), "row": 0})
    return state


def load_state() -> dict:
    if not STATE_PATH.exists():
        return fresh_state({"games_played": 0, "best_score": 0, "total_kills": 0})
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state.setdefault("stats", {"games_played": 0, "best_score": 0, "total_kills": 0})
    return state


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# ── rules ────────────────────────────────────────────────────────────────────

def apply_action(state: dict, action: str) -> str:
    if action == "left":
        state["rocket_col"] = max(0, state["rocket_col"] - 1)
        return f"Interceptor banked left — now in lane {state['rocket_col'] + 1}."
    if action == "right":
        state["rocket_col"] = min(COLS - 1, state["rocket_col"] + 1)
        return f"Interceptor banked right — now in lane {state['rocket_col'] + 1}."

    # fire
    lane = state["rocket_col"]
    targets = [e for e in state["enemies"] if e["col"] == lane]
    if not targets:
        return "Fired — no hostile in that lane. Missed."
    nearest = max(targets, key=lambda e: e["row"])
    state["enemies"].remove(nearest)
    state["score"] += 1
    return f"Direct hit! Score: {state['score']}."


def advance_wave(state: dict) -> bool:
    """Move hostiles down one step, spawn the next one, and settle a breach.
    Returns True if this turn ended the run."""
    for e in state["enemies"]:
        e["row"] += 1

    if any(e["row"] >= ROWS - 1 for e in state["enemies"]):
        state["status"] = "breached"
        state["stats"]["games_played"] += 1
        state["stats"]["best_score"] = max(state["stats"]["best_score"], state["score"])
        state["stats"]["total_kills"] += state["score"]
        return True

    spawn_chance = min(0.85, 0.25 + state["turn"] * 0.02)
    r = rng_for(state["seed"], state["turn"])
    if r.random() < spawn_chance:
        occupied = {e["col"] for e in state["enemies"] if e["row"] == 0}
        free = [c for c in range(COLS) if c not in occupied]
        if free:
            state["enemies"].append({"col": r.choice(free), "row": 0})

    state["turn"] += 1
    return False


# ── rendering ────────────────────────────────────────────────────────────────

def issue_link(title: str, body: str) -> str:
    query = urllib.parse.urlencode({"title": title, "body": body})
    return f"https://github.com/{REPO}/issues/new?{query}"


def action_link(action: str) -> str:
    return issue_link(
        f"move: {action}",
        f"Submitting this issue makes the interceptor {ACTION_LABEL[action]}.\n\n"
        "Nothing else needed — the board updates automatically and this issue "
        "closes itself. Leave the title exactly as it is.",
    )


def new_game_link() -> str:
    return issue_link(
        "game: new",
        "Submitting this issue launches a fresh interceptor run.",
    )


def render_block(state: dict) -> str:
    over = state["status"] != "active"
    rocket_col = state["rocket_col"]
    occupied = {(e["row"], e["col"]) for e in state["enemies"]}

    grid_rows = []
    for row in range(ROWS):
        cells = []
        for col in range(COLS):
            if row == ROWS - 1 and col == rocket_col and not over:
                cells.append("🚀")
            elif (row, col) in occupied:
                cells.append("👾")
            else:
                cells.append("⬛")
        grid_rows.append("| " + " | ".join(cells) + " |")
    header = "|" + "|".join([" "] * COLS) + "|"
    sep = "|" + "|".join(["---"] * COLS) + "|"
    grid = "\n".join([header, sep, *grid_rows])

    stats = state["stats"]

    if over:
        verdict = f"> `BREACH` **Perimeter compromised.** Final score: **{state['score']}**."
    else:
        verdict = f"> `LIVE` Score: **{state['score']}** · lane {rocket_col + 1}/{COLS} · your move."

    last = ""
    if state.get("last_actor") and state.get("last_action"):
        last = f"\nLast command: `{state['last_action']}` by **@{state['last_actor']}**\n"

    if over:
        controls = f"\n**[🚀 LAUNCH NEW INTERCEPTOR]({new_game_link()})**\n"
    else:
        controls = (
            "\n<div align=\"center\">\n\n"
            f"[**◀ LEFT**]({action_link('left')}) &nbsp;&nbsp; "
            f"[**🔫 FIRE**]({action_link('fire')}) &nbsp;&nbsp; "
            f"[**RIGHT ▶**]({action_link('right')})\n\n"
            "</div>\n"
            f"\n<sub>Want a clean run instead? **[relaunch]({new_game_link()})**.</sub>\n"
        )

    return f"""{BLOCK_START}
## `> orbital_defense --engage`

**Hostile packets are inbound from orbit. You fly the interceptor 🚀 — shoot
them down before one reaches the surface.**
Each command below opens a pre-filled issue; a workflow resolves it and
updates the board within about a minute.

<div align="center">

{grid}

</div>

{verdict}
{last}
| games played | best score | intrusions destroyed |
|---|---|---|
| {stats['games_played']} | {stats['best_score']} | {stats['total_kills']} |
{controls}
<sub>Spawn rate escalates with survival time — deterministic per run, not
predictable in advance. Source: [`game/engine.py`](game/engine.py).</sub>
{BLOCK_END}"""


def write_readme(state: dict) -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    if BLOCK_START not in readme or BLOCK_END not in readme:
        print("::error::README is missing the game markers.", file=sys.stderr)
        sys.exit(1)
    head, _, rest = readme.partition(BLOCK_START)
    _, _, tail = rest.partition(BLOCK_END)
    README_PATH.write_text(head + render_block(state) + tail, encoding="utf-8")


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_move(action: str, actor: str | None) -> str:
    action = action.strip().lower()
    state = load_state()

    if state["status"] != "active":
        return ("This run is already over. Use the **LAUNCH NEW INTERCEPTOR** "
                "link on the profile to start a fresh attempt.")

    if action not in ACTIONS:
        return f"`{action}` isn't a valid command. Use left, right, or fire."

    msg = apply_action(state, action)
    state["last_action"] = action
    state["last_actor"] = actor

    breached = advance_wave(state)
    save_state(state)
    write_readme(state)

    if breached:
        return f"{msg}\n\nA hostile reached the surface — **BREACH.** Final score: {state['score']}."
    return f"{msg}\n\nThe skies are still hot — your move."


def cmd_new() -> str:
    state = load_state()
    fresh = fresh_state(state["stats"])
    save_state(fresh)
    write_readme(fresh)
    return "New interceptor launched. Hostiles inbound — good luck."


def main() -> None:
    parser = argparse.ArgumentParser(description="ORBITAL DEFENSE engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_move = sub.add_parser("move")
    p_move.add_argument("action")
    p_move.add_argument("--actor", default=None)

    sub.add_parser("new")
    sub.add_parser("render")

    args = parser.parse_args()

    if args.command == "move":
        print(cmd_move(args.action, args.actor))
    elif args.command == "new":
        print(cmd_new())
    else:
        state = load_state()
        write_readme(state)
        print("Rendered.")


if __name__ == "__main__":
    main()
