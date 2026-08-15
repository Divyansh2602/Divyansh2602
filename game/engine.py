#!/usr/bin/env python3
"""INTRUSION GRID — the playable board on the profile README.

A visitor plays the intruder (X); the profile plays the firewall (O). GitHub
READMEs cannot run scripts, so every move arrives as an issue: each empty cell
on the board is a link that opens a pre-filled issue, a workflow feeds the
title to this script, and the rendered board is committed back.

The firewall searches the full game tree, so it cannot be beaten — noughts and
crosses is a solved draw. That is the hook, and it is honest: a perfect
intruder forces a stalemate, nothing better.

Usage:
    engine.py move <cell> [--actor <login>]   apply a visitor move, reply
    engine.py new                             reset the board
    engine.py render                          re-render the README block only
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.parse

REPO = "Divyansh2602/Divyansh2602"

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "game" / "state.json"
README_PATH = ROOT / "README.md"

BLOCK_START = "<!-- INTRUSION-GRID:START -->"
BLOCK_END = "<!-- INTRUSION-GRID:END -->"

INTRUDER = "X"
FIREWALL = "O"
EMPTY = " "

CELLS = ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"]
LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),   # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),   # columns
    (0, 4, 8), (2, 4, 6),              # diagonals
]

GLYPH = {
    INTRUDER: "🟥",
    FIREWALL: "🟦",
}

NEW_STATE = {
    "board": [EMPTY] * 9,
    "status": "active",       # active | breached | held | stalemate
    "last_move": None,
    "last_actor": None,
    "stats": {"breaches": 0, "holds": 0, "stalemates": 0},
}


# ── state ────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_PATH.exists():
        return json.loads(json.dumps(NEW_STATE))
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    # Carry stats across resets; everything else starts clean if malformed.
    state.setdefault("stats", {"breaches": 0, "holds": 0, "stalemates": 0})
    return state


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# ── rules ────────────────────────────────────────────────────────────────────

def winner(board: list[str]) -> str | None:
    for a, b, c in LINES:
        if board[a] != EMPTY and board[a] == board[b] == board[c]:
            return board[a]
    return None


def full(board: list[str]) -> bool:
    return EMPTY not in board


def minimax(board: list[str], maximizing: bool, depth: int = 0) -> tuple[int, int | None]:
    """Score the position for the firewall. Prefers faster wins, slower losses,
    so the firewall closes out a won game instead of stalling in it."""
    win = winner(board)
    if win == FIREWALL:
        return 10 - depth, None
    if win == INTRUDER:
        return depth - 10, None
    if full(board):
        return 0, None

    best_score = -99 if maximizing else 99
    best_move = None
    mark = FIREWALL if maximizing else INTRUDER

    for i in range(9):
        if board[i] != EMPTY:
            continue
        board[i] = mark
        score, _ = minimax(board, not maximizing, depth + 1)
        board[i] = EMPTY
        if (maximizing and score > best_score) or (not maximizing and score < best_score):
            best_score, best_move = score, i

    return best_score, best_move


def settle(state: dict) -> str | None:
    """Record a finished game exactly once. Returns the outcome, or None."""
    board = state["board"]
    win = winner(board)
    if win == INTRUDER:
        state["status"] = "breached"
        state["stats"]["breaches"] += 1
        return "breached"
    if win == FIREWALL:
        state["status"] = "held"
        state["stats"]["holds"] += 1
        return "held"
    if full(board):
        state["status"] = "stalemate"
        state["stats"]["stalemates"] += 1
        return "stalemate"
    return None


# ── rendering ────────────────────────────────────────────────────────────────

def issue_link(title: str, body: str) -> str:
    query = urllib.parse.urlencode({"title": title, "body": body})
    return f"https://github.com/{REPO}/issues/new?{query}"


def move_link(cell: str) -> str:
    return issue_link(
        f"move: {cell}",
        f"Submitting this issue plays {cell} on the intrusion grid.\n\n"
        "Nothing else needed — the board updates automatically and this issue "
        "closes itself. Leave the title exactly as it is.",
    )


def new_game_link() -> str:
    return issue_link(
        "game: new",
        "Submitting this issue resets the intrusion grid for a fresh attempt.",
    )


def render_block(state: dict) -> str:
    board = state["board"]
    over = state["status"] != "active"

    rows = ["| | 1 | 2 | 3 |", "|---|---|---|---|"]
    for r, label in enumerate("ABC"):
        cells = []
        for c in range(3):
            i = r * 3 + c
            mark = board[i]
            if mark != EMPTY:
                cells.append(GLYPH[mark])
            elif over:
                cells.append("⬛")
            else:
                cells.append(f"[⬛]({move_link(CELLS[i])})")
        rows.append(f"| **{label}** | " + " | ".join(cells) + " |")
    grid = "\n".join(rows)

    stats = state["stats"]
    played = stats["breaches"] + stats["holds"] + stats["stalemates"]

    if state["status"] == "breached":
        verdict = "> `ALERT` **Firewall breached.** You got through. Genuinely well played."
    elif state["status"] == "held":
        verdict = "> `SECURE` **Intrusion contained.** The firewall held."
    elif state["status"] == "stalemate":
        verdict = "> `STALEMATE` **Deadlock.** Nobody gets through — the best result available against a perfect defence."
    else:
        verdict = "> `LIVE` Your move. Click any ⬛ to place a node."

    last = ""
    if state.get("last_actor") and state.get("last_move"):
        last = f"\nLast probe: `{state['last_move']}` by **@{state['last_actor']}**\n"

    action = (
        f"\n**[⟳ RESET GRID]({new_game_link()})** — start a fresh attempt.\n"
        if over else
        f"\n<sub>Stuck? **[reset the grid]({new_game_link()})**.</sub>\n"
    )

    return f"""{BLOCK_START}
## `> intrusion_grid --play`

**You are the intruder 🟥. This profile is the firewall 🟦.**
Click a cell — it opens a pre-filled issue, and submitting it plays your move.
A workflow answers within about a minute.

<div align="center">

{grid}

</div>

{verdict}
{last}
| sessions | breaches | contained | stalemates |
|---|---|---|---|
| {played} | {stats['breaches']} | {stats['holds']} | {stats['stalemates']} |
{action}
<sub>The firewall searches the whole game tree, so it never loses. Noughts and
crosses is a solved draw — a stalemate *is* the win condition here. Source:
[`game/engine.py`](game/engine.py).</sub>
{BLOCK_END}"""


def write_readme(state: dict) -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    if BLOCK_START not in readme or BLOCK_END not in readme:
        print("::error::README is missing the INTRUSION-GRID markers.", file=sys.stderr)
        sys.exit(1)
    head, _, rest = readme.partition(BLOCK_START)
    _, _, tail = rest.partition(BLOCK_END)
    README_PATH.write_text(head + render_block(state) + tail, encoding="utf-8")


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_move(cell: str, actor: str | None) -> str:
    cell = cell.strip().upper()
    state = load_state()

    if state["status"] != "active":
        return ("This round is already over. Use the **RESET GRID** link on the "
                "profile to start a fresh attempt.")

    if cell not in CELLS:
        return f"`{cell}` is not a cell on the grid. Valid cells are A1–C3."

    idx = CELLS.index(cell)
    if state["board"][idx] != EMPTY:
        return f"`{cell}` is already taken. Pick an empty cell."

    state["board"][idx] = INTRUDER
    state["last_move"] = cell
    state["last_actor"] = actor

    outcome = settle(state)
    reply_tail = ""

    if outcome is None:
        _, ai_move = minimax(state["board"], maximizing=True)
        if ai_move is not None:
            state["board"][ai_move] = FIREWALL
            reply_tail = f" The firewall answered at `{CELLS[ai_move]}`."
        outcome = settle(state)

    save_state(state)
    write_readme(state)

    if outcome == "breached":
        return f"You played `{cell}`.{reply_tail}\n\n**Firewall breached.** You beat it — that is not supposed to happen. Nice."
    if outcome == "held":
        return f"You played `{cell}`.{reply_tail}\n\n**Contained.** The firewall closed the line."
    if outcome == "stalemate":
        return f"You played `{cell}`.{reply_tail}\n\n**Stalemate** — the best result available against a perfect defence."
    return f"You played `{cell}`.{reply_tail}\n\nYour move — the board on the profile is updated."


def cmd_new() -> str:
    state = load_state()
    fresh = json.loads(json.dumps(NEW_STATE))
    fresh["stats"] = state["stats"]
    save_state(fresh)
    write_readme(fresh)
    return "Grid reset. The board on the profile is clear — your move."


def main() -> None:
    parser = argparse.ArgumentParser(description="INTRUSION GRID engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_move = sub.add_parser("move")
    p_move.add_argument("cell")
    p_move.add_argument("--actor", default=None)

    sub.add_parser("new")
    sub.add_parser("render")

    args = parser.parse_args()

    if args.command == "move":
        print(cmd_move(args.cell, args.actor))
    elif args.command == "new":
        print(cmd_new())
    else:
        state = load_state()
        write_readme(state)
        print("Rendered.")


if __name__ == "__main__":
    main()
