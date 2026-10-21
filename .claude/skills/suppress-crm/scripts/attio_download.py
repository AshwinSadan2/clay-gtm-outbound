#!/usr/bin/env python3
"""Stage 2 of 3: download the Attio suppression list. Read-only on Attio.

Writes (date stamp = --date, default today):
    data/raw/attio_<object>_<date>.jsonl                  every Attio record exactly as returned
    data/processed/suppression_attio_<level>_<date>.csv   one row per suppressed domain (domain level) or person (contact level)

Usage (from the project folder; use the flags signed off at stage 1):
    .venv/bin/python .claude/skills/suppress-crm/scripts/attio_download.py \
        --level domain --categories all --days 90

Next stage: attio_suppress.py (preview first, then --apply).
"""
import attio_common as ac


def main():
    parser = ac.base_parser(__doc__ + "\n" + ac.__doc__.split("\n\n", 1)[1])
    ac.add_category_args(parser)
    args = ac.setup(parser)
    raw_dir = ac.ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows, crm = ac.classify(args, raw_dir)
    out = ac.suppression_file(args.level, args.date)
    ac.write_csv(out, ac.LIST_COLUMNS[args.level], rows)
    ac.report(rows, args.detail_threshold, "Downloaded suppression list", args.level)
    ac.logging.info("download: %d entries → %s | raw → data/raw/attio_*_%s.jsonl | %s",
                    len(rows), out.relative_to(ac.ROOT), args.date, ac.describe(args))


if __name__ == "__main__":
    main()
