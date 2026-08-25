import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from analyze_ranker_metrics import find_results_sheet
from openpyxl import load_workbook


DEFAULT_SCORE_COLUMNS = ("aragorn_score", "arax_score")
DEFAULT_RANK_COLUMNS = {
    "aragorn_score": "aragorn_rank",
    "arax_score": "arax_rank",
}
DEFAULT_GROUP_COLUMNS = ("qid", "ARA", "edge_id")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Post-process a ranker comparison workbook by collapsing duplicate "
            "edge rows, taking max score per ranker, and recomputing ranks."
        )
    )
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument(
        "--sheet",
        type=str,
        default=None,
        help="Results sheet to dedupe. If omitted, auto-detects the ranker result sheet.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output workbook path. Defaults to <input_stem>_deduped.xlsx.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional JSON report path. Defaults next to the output workbook.",
    )
    return parser.parse_args()


def normalize_blank(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def first_non_blank(values: pd.Series) -> Any:
    for value in values:
        normalized = normalize_blank(value)
        if normalized is not None:
            return normalized
    return None


def merge_labels(values: pd.Series) -> str | None:
    labels = sorted({str(value) for value in values if normalize_blank(value) is not None})
    if not labels:
        return None
    if len(labels) == 1:
        return labels[0]
    return "|".join(labels)


def merge_bool(values: pd.Series) -> bool | None:
    normalized = [normalize_blank(value) for value in values]
    normalized = [value for value in normalized if value is not None]
    if not normalized:
        return None
    return any(bool(value) for value in normalized)


def detect_results_sheet(workbook_path: Path, requested_sheet: str | None) -> str:
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    return find_results_sheet(workbook, requested_sheet).title


def conflict_columns(df: pd.DataFrame, group_columns: list[str]) -> dict[str, int]:
    ignored = set(group_columns) | {
        *DEFAULT_SCORE_COLUMNS,
        *DEFAULT_RANK_COLUMNS.values(),
        "rank diff (aragorn-arax)",
    }
    conflicts = {}
    grouped = df.groupby(group_columns, dropna=False)
    for column in df.columns:
        if column in ignored:
            continue
        conflict_count = 0
        for _, group in grouped:
            values = {normalize_blank(value) for value in group[column]}
            values.discard(None)
            if len(values) > 1:
                conflict_count += 1
        if conflict_count:
            conflicts[column] = conflict_count
    return conflicts


def dedupe_results_sheet(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    missing = [column for column in DEFAULT_GROUP_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required grouping columns: {missing}")

    group_columns = list(DEFAULT_GROUP_COLUMNS)
    duplicate_sizes = df.groupby(group_columns, dropna=False).size()
    duplicate_groups = duplicate_sizes[duplicate_sizes > 1]
    conflicts = conflict_columns(df, group_columns)

    aggregations = {}
    for column in df.columns:
        if column in group_columns:
            continue
        if column in DEFAULT_SCORE_COLUMNS:
            aggregations[column] = "max"
        elif column == "expected_output":
            aggregations[column] = merge_labels
        elif column == "is_direct_edge":
            aggregations[column] = merge_bool
        elif column in DEFAULT_RANK_COLUMNS.values() or column == "rank diff (aragorn-arax)":
            continue
        else:
            aggregations[column] = first_non_blank

    deduped = (
        df.groupby(group_columns, dropna=False, as_index=False)
        .agg(aggregations)
        .copy()
    )

    rank_group_columns = ["qid", "ARA"]
    for score_column, rank_column in DEFAULT_RANK_COLUMNS.items():
        if score_column not in deduped.columns:
            continue
        numeric_scores = pd.to_numeric(deduped[score_column], errors="coerce")
        deduped[rank_column] = (
            numeric_scores.groupby([deduped[column] for column in rank_group_columns])
            .rank(ascending=False, method="min")
            .astype("Int64")
        )

    if {"aragorn_rank", "arax_rank"} <= set(deduped.columns):
        deduped["rank diff (aragorn-arax)"] = (
            deduped["aragorn_rank"] - deduped["arax_rank"]
        ).astype("Int64")

    desired_order = [
        "qid",
        "ARA",
        "expected_output",
        "subject_id",
        "subject_name",
        "object_id",
        "object_name",
        "predicate",
        "aragorn_score",
        "arax_score",
        "aragorn_rank",
        "arax_rank",
        "rank diff (aragorn-arax)",
        "edge_id",
        "is_direct_edge",
    ]
    ordered_columns = [column for column in desired_order if column in deduped.columns]
    ordered_columns.extend(column for column in deduped.columns if column not in ordered_columns)
    deduped = deduped[ordered_columns]

    sort_columns = [
        column
        for column in ("qid", "ARA", "aragorn_rank", "arax_rank", "edge_id")
        if column in deduped.columns
    ]
    deduped = deduped.sort_values(sort_columns, na_position="last").reset_index(drop=True)

    label_counts = Counter(
        str(value) if normalize_blank(value) is not None else "Unlabeled"
        for value in deduped.get("expected_output", [])
    )
    report = {
        "raw_rows": int(len(df)),
        "deduped_rows": int(len(deduped)),
        "duplicate_groups": int(len(duplicate_groups)),
        "duplicate_rows": int(duplicate_groups.sum()),
        "max_duplicate_group_size": int(duplicate_groups.max()) if len(duplicate_groups) else 0,
        "conflict_columns": conflicts,
        "deduped_label_counts": dict(sorted(label_counts.items())),
    }
    return deduped, report


def main() -> None:
    args = parse_args()
    output = args.output or args.workbook.with_name(
        f"{args.workbook.stem}_deduped{args.workbook.suffix}"
    )
    report_path = args.report or output.with_name(f"{output.stem}_dedupe_report.json")

    result_sheet = detect_results_sheet(args.workbook, args.sheet)
    sheets = pd.read_excel(args.workbook, sheet_name=None)
    if result_sheet not in sheets:
        raise ValueError(f"Sheet {result_sheet!r} not found in {args.workbook}")

    deduped_results, report = dedupe_results_sheet(sheets[result_sheet])
    sheets[result_sheet] = deduped_results

    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output) as writer:
        for sheet_name, sheet_df in sheets.items():
            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)

    report = {
        "input_workbook": str(args.workbook),
        "output_workbook": str(output),
        "sheet": result_sheet,
        **report,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Deduped ranker workbook")
    print(f"  Input: {args.workbook}")
    print(f"  Output: {output}")
    print(f"  Sheet: {result_sheet}")
    print(f"  Raw rows: {report['raw_rows']}")
    print(f"  Deduped rows: {report['deduped_rows']}")
    print(f"  Duplicate groups: {report['duplicate_groups']}")
    print(f"  Duplicate rows: {report['duplicate_rows']}")
    print(f"  Report: {report_path}")


if __name__ == "__main__":
    main()
