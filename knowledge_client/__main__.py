"""python -m knowledge_client --bundle-dir /tmp/knowledge-1.2.0 --query bisagras"""
import argparse
import json
import sys

from .reader import BundleError, load_bundle, search_content


def main() -> int:
    parser = argparse.ArgumentParser(description="Busca conocimiento con cita al libro.")
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    try:
        result = search_content(load_bundle(args.bundle_dir), args.query, args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except BundleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
