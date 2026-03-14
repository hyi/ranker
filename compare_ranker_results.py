import argparse
import json
import pandas as pd


def extract_results(json_data, ranker_name):
    message = json_data["message"]
    node_name, edge_info = build_kg_maps(message)

    rows = []
    for r in message["results"]:
        subject_ids = [x["id"] for x in r["node_bindings"].get("SN", [])]
        object_ids = [x["id"] for x in r["node_bindings"].get("ON", [])]
        for analysis in r.get("analyses", []):
            score = round(analysis.get("score", 0), 3)
            edge_bindings = analysis.get("edge_bindings", {})
            for bindings in edge_bindings.values():
                for b in bindings:
                    eid = b["id"]
                    info = edge_info.get(eid, {})
                    for s in subject_ids:
                        for o in object_ids:
                            rows.append({
                                "subject_id": s,
                                "subject_name": node_name.get(s, s),
                                "object_id": o,
                                "object_name": node_name.get(o, o),
                                "predicate": info.get("predicate"),
                                "edge_id": eid,
                                f"{ranker_name}_score": score
                            })

    df = pd.DataFrame(rows)
    # rank descending (higher score = better)
    df[f"{ranker_name}_rank"] = (df[f"{ranker_name}_score"].rank(ascending=False, method="min").astype(int))

    return df


def build_kg_maps(message):
    nodes = message["knowledge_graph"]["nodes"]
    edges = message["knowledge_graph"]["edges"]

    node_name = {
        nid: n.get("name", nid)
        for nid, n in nodes.items()
    }

    edge_info = {}
    for eid, edge in edges.items():
        predicate = edge.get("predicate")
        edge_info[eid] = {
            "predicate": predicate,
        }

    return node_name, edge_info


def compare_rankers(aragorn_file, arax_file):
    with open(aragorn_file) as f:
        aragorn_data = json.load(f)

    with open(arax_file) as f:
        arax_data = json.load(f)

    df_aragorn = extract_results(aragorn_data, "aragorn")
    df_arax = extract_results(arax_data, "arax")

    merged = pd.merge(df_aragorn, df_arax,
                      on=[
                          "subject_id",
                          "object_id",
                          "edge_id",
                          "subject_name",
                          "object_name",
                          "predicate"
                      ],
                      how="outer")

    merged["score diff (aragorn-arax"] = merged["aragorn_score"] - merged["arax_score"]
    merged["rank diff (aragorn-arax)"] = merged["aragorn_rank"] - merged["arax_rank"]

    merged = merged.sort_values("aragorn_rank")
    desired_column_order = ['subject_id', 'subject_name', 'object_id', 'object_name',
                            'predicate', 'aragorn_score', 'arax_score', 'aragorn_rank', 'arax_rank',
                            'score diff (aragorn-arax', 'rank diff (aragorn-arax)', 'edge_id']
    return merged[desired_column_order]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process arguments.')
    parser.add_argument('--input_file', type=str, required=False,
                        default='results/query3/shepherd_{}_{}_score_response_no_direct_edges.json',
                        help='input file pattern of the results with {} to be filled in with two rankers')
    parser.add_argument('--input_query_file', type=str, required=False,
                        default='results/query3/input_query.json')
    parser.add_argument('--output_file', type=str, required=False,
                        default='results/query3/query_shepherd_ranker_comparison.xlsx',
                        help='output file for the comparison result')

    args = parser.parse_args()
    input_file = args.input_file
    input_query_file = args.input_query_file
    output_file = args.output_file

    with open(input_query_file) as f:
        query = json.load(f)
    query_lines = json.dumps(query, indent=2).split("\n")
    query_df = pd.DataFrame({"query": query_lines})

    df_aragorn = compare_rankers(input_file.format('aragorn', 'aragorn'), input_file.format('aragorn', 'arax'))
    df_arax = compare_rankers(input_file.format('arax', 'aragorn'), input_file.format('arax', 'arax'))
    df_bte = compare_rankers(input_file.format('bte', 'aragorn'), input_file.format('bte', 'arax'))

    with pd.ExcelWriter(output_file) as writer:
        query_df.to_excel(writer, sheet_name="input_query", index=False)
        df_aragorn.to_excel(writer, sheet_name="Aragorn_ARA", index=False)
        df_arax.to_excel(writer, sheet_name="ARAX_ARA", index=False)
        df_bte.to_excel(writer, sheet_name="BTE_ARA", index=False)

    exit(0)

