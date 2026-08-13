"""Argparse helpers for CLI and agent-skill documentation tests."""

from __future__ import annotations

import argparse


def leaf_commands(
    parser: argparse.ArgumentParser,
    prefix: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], argparse.ArgumentParser]]:
    subparsers = next(
        (action for action in parser._actions if isinstance(action, argparse._SubParsersAction)),
        None,
    )
    if subparsers is None:
        return [(prefix, parser)]
    leaves: list[tuple[tuple[str, ...], argparse.ArgumentParser]] = []
    for name, child in subparsers.choices.items():
        leaves.extend(leaf_commands(child, (*prefix, name)))
    return leaves
