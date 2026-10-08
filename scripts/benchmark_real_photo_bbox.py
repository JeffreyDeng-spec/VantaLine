#!/usr/bin/env python3
"""Score privately exported annotations only after independent human review."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.training.bbox_benchmark import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--mask', type=Path, required=True)
    parser.add_argument('--doubao', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding='utf-8'))
    result = evaluate(load(args.reference), {'mask': load(args.mask), 'doubao': load(args.doubao)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Completed offline comparison; result written to private output file.')


if __name__ == '__main__':
    main()
