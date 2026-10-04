from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .ableton import inspect_set, prepare_render, import_revision
from .common import SyncError
from .engine import DATA, publish, publish_completed
from .package import validate


def main():
    p = argparse.ArgumentParser(description="Ableton Live ↔ REAPER audio collaboration")
    sub = p.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Read a Live 12 set without changing it")
    inspect.add_argument("source", type=Path)
    prepare = sub.add_parser("prepare", help="Make an isolated render copy")
    prepare.add_argument("source", type=Path)
    prepare.add_argument("job", type=Path)
    prepare.add_argument("--loop", action="store_true")
    prepare.add_argument("--tail", type=float, default=4)
    for cmd in ("publish", "publish-renders"):
        parser = sub.add_parser(cmd)
        parser.add_argument("source" if cmd == "publish" else "job", type=Path)
        parser.add_argument("exchange", type=Path)
        parser.add_argument("--project-id", required=True)
        if cmd == "publish":
            parser.add_argument("--whole-timeline", action="store_true")
    check = sub.add_parser("validate")
    check.add_argument("revision", type=Path)
    receive = sub.add_parser("import")
    receive.add_argument("revision", type=Path)
    receive.add_argument("destination", type=Path)
    receive.add_argument("--original", type=Path)
    args = p.parse_args()
    try:
        if args.command == "inspect":
            result = asdict(inspect_set(args.source))
        elif args.command == "prepare":
            result = prepare_render(args.source, args.job, args.tail, args.loop)
        elif args.command == "validate":
            result = validate(args.revision)
        elif args.command == "import":
            result = import_revision(args.revision, args.destination, args.original)
        elif args.command == "publish-renders":
            result = publish_completed(args.job, args.exchange, args.project_id, DATA / "state.sqlite")
        else:
            result = publish(args.source, args.exchange, args.project_id, use_loop=not args.whole_timeline, log=print)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    except (SyncError, OSError) as exc:
        p.exit(1, f"DAWSync: {exc}\n")


if __name__ == "__main__":
    main()
