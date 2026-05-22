import json
import argparse
import pandas as pd
from pathlib import Path
from create_ranker_query_data import filter_trapi_message
from ranker_scoring import run_query
from compare_ranker_results import compare_rankers


ARAS = ["aragorn", "arax", "bte"]
RANKERS = ["aragorn", "arax"]

LOOKUP_WORKFLOWS = {
    "aragorn": "aragorn.lookup",
    "arax": "lookup",
    "bte": "bte.lookup"
}

LOOKUP_URLS = {
    "aragorn": "https://shepherd.renci.org/aragorn/query",
    "arax": "https://shepherd.renci.org/arax/query",
    "bte": "https://shepherd.renci.org/bte/query"
}

RANKER_WORKFLOWS = {
    "aragorn": [
        {"id": "aragorn.omnicorp"},
        {"id": "aragorn.score"},
        {"id": "sort_results_score"},
        {"id": "filter_results_top_n", "parameters": {"max_results": 500}},
        {"id": "filter_kgraph_orphans"},
    ],
    "arax": [
        {"id": "arax.rank"},
        {"id": "sort_results_score"},
        {"id": "filter_results_top_n", "parameters": {"max_results": 500}},
        {"id": "filter_kgraph_orphans"},
    ]
}


def process_query(qid, query, expected_outputs):
    sheets = {}
    for ara in ARAS:
        print(f"{qid} lookup via {ara}")
        lookup_payload = {
            **query,
            "workflow": [{"id": LOOKUP_WORKFLOWS[ara]}]
        }
        lookup_resp = run_query(lookup_payload, url=LOOKUP_URLS[ara])
        if not lookup_resp:
            print('lookup_resp is empty')
            continue
        if "message" not in lookup_resp:
            print(f'lookup_resp does not contain message key: {lookup_resp}')
            continue

        if not "knowledge_graph" in lookup_resp["message"]:
            print(f"knowledge_graph key is not in response message: {lookup_resp['message']}")
            continue

        filtered_message = filter_trapi_message(lookup_resp["message"])
        ranker_responses = {}

        for ranker in RANKERS:
            print(f"  scoring with {ranker}")
            payload = {
                "message": filtered_message,
                "workflow": RANKER_WORKFLOWS[ranker]
            }
            response = run_query(payload)
            ranker_responses[ranker] = response

        df = compare_rankers(ranker_responses["aragorn"], ranker_responses["arax"], expected_outputs)
        sheets[f"{ara.upper()}_ARA"] = df
    return sheets


def write_results(out, query_rows, all_results):
    """Write current accumulated results to Excel, overwriting the previous checkpoint."""
    df_results = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
    df_queries = pd.DataFrame(query_rows)

    if not df_results.empty:
        df_results = df_results[["qid", "ARA"] + [c for c in df_results.columns if c not in ("qid", "ARA")]]

    with pd.ExcelWriter(out) as writer:
        df_queries.to_excel(writer, sheet_name="input_query", index=False)
        if not df_results.empty:
            df_results.to_excel(writer, sheet_name="ARA_Ranker_Results", index=False)

    print(f"checkpoint saved to {out} ({len(query_rows)} queries, {len(all_results)} result frames)")


def load_existing_results(out):
    """Load previously saved results from an existing output file for resume support."""
    out_path = Path(out)
    if not out_path.exists():
        return [], [], set()

    print(f"found existing output at {out}, loading for resume...")
    query_rows = []
    all_results = []
    completed_qids = set()

    try:
        df_queries = pd.read_excel(out, sheet_name="input_query")
        for _, row in df_queries.iterrows():
            query_rows.append({"qid": row["qid"], "query": row["query"]})
            completed_qids.add(row["qid"])
    except Exception as e:
        print(f"warning: could not read input_query sheet: {e}")

    try:
        df_results = pd.read_excel(out, sheet_name="ARA_Ranker_Results")
        if not df_results.empty:
            all_results.append(df_results)
    except Exception as e:
        print(f"warning: could not read ARA_Ranker_Results sheet: {e}")

    print(f"resuming — {len(completed_qids)} queries already completed: {sorted(completed_qids)}")
    return query_rows, all_results, completed_qids


def main(query_file, out):
    with open(query_file) as f:
        queries = json.load(f)

    query_rows, all_results, completed_qids = load_existing_results(out)

    for qid, query in enumerate(queries["queries"]):
        if qid in completed_qids:
            print(f"skipping qid {qid} (already completed)")
            continue

        expected_outputs = query["expected_outputs"]
        query = query["trapi_query"]
        qry_sheets = process_query(qid, query, expected_outputs)

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
                        default='data/test_queries/sprint_6_tests.json',
                        help='input file of test queries')
    parser.add_argument('--out_file', type=str, required=False,
                        default='results/arax_bespoke_ranker/ranker_comparison_test_queries.xlsx',
                        help='output file pattern of test queries')

    args = parser.parse_args()
    input_file = args.input_file
    out_file = args.out_file
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    main(input_file, out_file)
