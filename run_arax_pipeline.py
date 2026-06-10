import json
import argparse
import pandas as pd
from pathlib import Path
from create_ranker_query_data import filter_trapi_message, annotate_trapi_edges
from ranker_scoring import run_query
from compare_ranker_results import compare_rankers
from run_pipeline import load_existing_results, write_results


ARAGORN_RANKER_WORKFLOW = [
    {"id": "aragorn.omnicorp"},
    {"id": "aragorn.score"},
    {"id": "sort_results_score"},
    {"id": "filter_results_top_n", "parameters": {"max_results": 500}},
    {"id": "filter_kgraph_orphans"},
]


ARAX_URL = 'https://arax.ci.transltr.io/api/arax/v1.4/query'

def process_query(qid:int, query:dict, expected_outputs:str):
    # get MVP-specific ranker responses from ARAX
    sheets = {}
    print(f"getting MVP-specific ranker responses for query {qid}")
    payload = {
        **query,
        "submitter": "ranker comparison"
    }
    resp = run_query(payload, url=ARAX_URL)
    if not resp:
        print(f'Skipping this query with payload: {payload} since ARAX response is empty')
        return sheets
    if "message" not in resp:
        print(f'Skipping this query with payload: {payload} since ARAX resp does not contain message key: {resp}')
        return sheets
    if not "results" in resp["message"]:
        print(f"Skipping this query with payload: {payload} since knowledge_graph key is not in response "
              f"message: {resp['message']}")
        return sheets

    annotated_message = annotate_trapi_edges(resp["message"])
    ranker_responses = {
        'arax': resp
    }

    payload_msg_to_aragorn_ranker = annotated_message.copy()
    print("  scoring with aragorn ranker")
    payload = {
        "message": payload_msg_to_aragorn_ranker,
        "workflow": ARAGORN_RANKER_WORKFLOW
    }
    aragorn_response = run_query(payload)
    ranker_responses['aragorn'] = aragorn_response

    df = compare_rankers(ranker_responses["aragorn"], ranker_responses["arax"], expected_outputs, sort_by='arax_rank')
    sheets["ARAX_ARA"] = df
    return sheets


def main(query_file, out):
    with open(query_file) as f:
        queries = json.load(f)

    query_rows, all_results, completed_qids = load_existing_results(out, data_sheet_name="Ranker_Results")

    for qid, query in enumerate(queries["queries"]):
        if qid in completed_qids:
            print(f"skipping qid {qid} (already completed)")
            continue

        expected_outputs = query["expected_outputs"]
        query = query["trapi_query"]

        qry_sheets = process_query(qid, query, expected_outputs)
        if not qry_sheets:
            # skipping this query
            continue

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
                        default='results/arax_bespoke_ranker/ranker_comparison_test_queries.xlsx',
                        help='output file pattern of test queries')

    args = parser.parse_args()

    Path(args.out_file).parent.mkdir(parents=True, exist_ok=True)
    main(args.input_file, args.out_file)
