import json
import argparse
import pandas as pd
from pathlib import Path
from create_ranker_query_data import filter_trapi_message
from ranker_scoring import run_query
from compare_ranker_results import extract_results, compare_rankers


ARAS = ["aragorn", "arax", "bte"]
RANKERS = ["aragorn", "arax"]

LOOKUP_WORKFLOWS = {
    "aragorn": "aragorn.lookup",
    "arax": "lookup",
    "bte": "bte.lookup"
}

RANKER_WORKFLOWS = {
    "aragorn": [
        {"id": "aragorn.omnicorp"},
        {"id": "aragorn.score"}
    ],
    "arax": [
        {"id": "arax.rank"}
    ]
}


def process_query(qid, query):
    sheets = {}
    for ara in ARAS:
        print(f"{qid} lookup via {ara}")
        lookup_payload = {
            **query,
            "workflow": [{"id": LOOKUP_WORKFLOWS[ara]}]
        }
        lookup_resp = run_query(lookup_payload)

        if "message" not in lookup_resp:
            print(lookup_resp)
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
            ranker_responses[ranker] = run_query(payload)

        df = compare_rankers(ranker_responses["aragorn"], ranker_responses["arax"])
        sheets[f"{ara.upper()}_ARA"] = df
    return sheets


def main(query_file, out_file_pattern):
    with open(query_file) as f:
        queries = json.load(f)

    for qid, query in enumerate(queries):
        qry_sheets = process_query(qid, query)
        out = out_file_pattern.format(f'query{qid}')
        with pd.ExcelWriter(out) as writer:
            pd.DataFrame({"query": json.dumps(query, indent=2).split("\n")}
                         ).to_excel(writer, sheet_name="input_query", index=False)

            for name, df in qry_sheets.items():
                if df is not None and not df.empty:
                    df.to_excel(writer, sheet_name=name, index=False)

        print(f"saved {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process arguments.')
    parser.add_argument('--input_file', type=str, required=False,
                        default='data/test_queries/test_queries.json',
                        help='input file of test queries')
    parser.add_argument('--out_file', type=str, required=False,
                        default='results/test_queries/ranker_comparison_{}.xlsx',
                        help='output file pattern of test queries')

    args = parser.parse_args()
    input_file = args.input_file
    out_file = args.out_file
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    main(input_file, out_file)
