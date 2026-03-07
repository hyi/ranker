import argparse
import json


def filter_trapi_message(message):
    kg = message["knowledge_graph"]

    edges = kg["edges"]
    nodes = kg["nodes"]

    # determine supported edges
    supported_edges = set()

    for eid, edge in edges.items():
        attrs = edge.get("attributes", [])
        for attr in attrs:
            if attr.get("attribute_type_id") == "biolink:support_graphs":
                supported_edges.add(eid)
                break

    referenced_edges = set()
    new_results = []

    # filter out direct edges not included in supported edges in results
    for result in message["results"]:
        keep_result = False

        for analysis in result.get("analyses", []):
            edge_bindings = analysis.get("edge_bindings", {})
            new_edge_bindings = {}

            for key, bindings in edge_bindings.items():
                kept = []

                for b in bindings:
                    eid = b["id"]
                    if eid in supported_edges:
                        kept.append(b)
                        referenced_edges.add(eid)
                        keep_result = True

                if kept:
                    new_edge_bindings[key] = kept

            analysis["edge_bindings"] = new_edge_bindings

        if keep_result:
            new_results.append(result)

    message["results"] = new_results

    # prune edges from kg to remove direct edges
    new_edges = {eid: edges[eid] for eid in referenced_edges if eid in edges}
    kg["edges"] = new_edges

    # collect referenced nodes
    referenced_nodes = set()

    for edge in new_edges.values():
        referenced_nodes.add(edge["subject"])
        referenced_nodes.add(edge["object"])

    # prune nodes from kg to remove those not referenced in support edges
    kg["nodes"] = {nid: nodes[nid] for nid in referenced_nodes if nid in nodes}

    return message


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process arguments.')
    parser.add_argument('--input_file', type=str, required=False,
                        default='data/shepherd_bte_response.json',
                        help='input file of the workflow lookup response')
    parser.add_argument('--score_source', type=str, required=False,
                        default='arax',
                        help='score source: either aragorn or arax')
    parser.add_argument('--output_file', type=str, required=False,
                        default='data/bte_arax_score_query_no_direct_edges.json',
                        help='output file for the score query formed from input file')

    args = parser.parse_args()
    input_file = args.input_file
    score_source = args.score_source
    output_file = args.output_file


    with open(input_file, 'r') as f:
        lookup_data = json.load(f)

    if score_source == 'arax':
        score_id = 'score'
    elif score_source == 'aragorn':
        score_id = 'aragorn.score'
    else:
        print(f'wrong input score_source: {score_source}')
        exit(1)

    print(f'score_id: {score_id}')

    score_dict = {
            "message": filter_trapi_message(lookup_data['message']),
            "workflow": [
                {"id": score_id}
            ]
        }
    print(f'score_dict workflow: {score_dict["workflow"]}')
    print(f"output_file: {output_file}")
    with open(output_file, 'w') as f:
        json.dump(score_dict, f, indent=2)
    print('Done')
