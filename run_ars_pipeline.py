import json
import argparse
import pandas as pd
from pathlib import Path
from create_ranker_query_data import annotate_trapi_edges
from ranker_scoring import run_query
from compare_ranker_results import compare_rankers
from run_pipeline import RANKERS, write_results, load_existing_results
from ars_query import run_ars_query, ARS_BASE_URL

RANKER_WORKFLOWS = {
    "aragorn": [
        {"id": "aragorn.omnicorp"},
        {"id": "aragorn.score"},
    ],
    "arax": [
        {"id": "arax.rank"},
    ]
}


def process_query(qid, query, expected_outputs, base_url):
    sheets = {}

    print(f"{qid} submitting to ARS at {base_url}")
    payload = {
        **query,
        "submitter": "ranker comparison"
    }
    # NOTE: no "workflow" — the ARS routes the query to the ARAs itself.
    merged = run_ars_query(payload, base_url=base_url)
    merged = merged["fields"]["data"]
    if not merged:
        print('ARS merged response is empty')
        return sheets
    if "message" not in merged:
        print(f'ARS merged response does not contain message key: {merged}')
        return sheets
    if "knowledge_graph" not in merged["message"]:
        print(f"knowledge_graph key is not in ARS message: {merged['message']}")
        return sheets
    if "results" not in merged["message"]:
        print(f"results key is not in ARS message: {merged['message']}")
        return sheets

    annotated_message = annotate_trapi_edges(merged["message"])

    ranker_responses = {}
    for ranker in RANKERS:
        print(f"  scoring with {ranker}")
        payload = {
            "message": annotated_message,
            "workflow": RANKER_WORKFLOWS[ranker]
        }
        ranker_responses[ranker] = run_query(payload)

    df = compare_rankers(ranker_responses["aragorn"], ranker_responses["arax"], expected_outputs)
    sheets["ARS"] = df
    return sheets


def main(query_file, out, base_url):
    with open(query_file) as f:
        queries = json.load(f)

    query_rows, all_results, completed_qids = load_existing_results(out, data_sheet_name='ARS')

    for qid, query in enumerate(queries["queries"]):
        if qid in completed_qids:
            print(f"skipping qid {qid} (already completed)")
            continue

        expected_outputs = query["expected_outputs"]
        query = query["trapi_query"]
        qry_sheets = process_query(qid, query, expected_outputs, base_url)

        query_rows.append({
            "qid": qid,
            "query": json.dumps(query, indent=2)
        })

        for name, df in qry_sheets.items():
            if df is not None and not df.empty:
                df2 = df.assign(qid=qid, ARA=name)
                all_results.append(df2)

        # Write after every query so partial results survive crashes/hangs
        write_results(out, query_rows, all_results)

    print(f"done — final output at {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process arguments.')
    parser.add_argument('--input_file', type=str, required=False,
                        default='data/test_queries/trapi_queries.json',
                        help='input file of test queries')
    parser.add_argument('--out_file', type=str, required=False,
                        default='results/ars/ranker_comparison_test_queries.xlsx',
                        help='output file pattern of test queries')
    parser.add_argument('--ars_url', type=str, required=False,
                        default=ARS_BASE_URL,
                        help='base URL of the ARS environment to query')

    args = parser.parse_args()

    Path(args.out_file).parent.mkdir(parents=True, exist_ok=True)
    main(args.input_file, args.out_file, args.ars_url)
