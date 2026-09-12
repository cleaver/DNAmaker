"""Local diagnostics and fixture utilities: python -m snapgene --help."""

import argparse
import json
import sys

from agent.errors import WorkflowError
from agent.models import ConstructRef
from .adapter import create_service


def main():
    parser = argparse.ArgumentParser(description="Local SnapGene bridge utilities. Agent workflows must validate before export/open.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("health")
    for name in ("convert", "export", "render", "open"):
        sub = commands.add_parser(name)
        sub.add_argument("input")
        sub.add_argument("--format", choices=("genbank", "fasta", "snapgene"), default="snapgene" if name != "convert" else "genbank")
        if name != "open":
            sub.add_argument("output")
        if name == "export":
            sub.add_argument("--output-format", choices=("genbank", "fasta"), default="genbank")
    args = parser.parse_args()
    service = create_service()
    try:
        if args.command == "health":
            result = service.health()
        else:
            ref = ConstructRef(args.input, args.format)
            if args.command == "convert":
                result = service.convert(ref, output_path=args.output).to_dict()
            elif args.command == "export":
                result = service.export(ref, output_path=args.output, output_format=args.output_format).to_dict()
            elif args.command == "render":
                result = {"path": service.render_map(ref, output_path=args.output)}
            else:
                service.open(ref)
                result = {"opened": ref.to_dict()}
        print(json.dumps({"ok": True, "result": result}))
    except WorkflowError as error:
        print(json.dumps(error.to_dict()))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
