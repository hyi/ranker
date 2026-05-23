#!/usr/bin/env python3
"""Extract unique TRAPI queries from test cases with all expected outputs."""

import copy
import json
import sys

import httpx
from tqdm import tqdm

NODE_NORM_URL = {
    "dev": "https://nodenormalization-sri.renci.org/1.4",
    "ci": "https://nodenorm.ci.transltr.io",
    "test": "https://nodenorm.test.transltr.io/1.4",
    "prod": "https://nodenorm.transltr.io/1.4",
}


def normalize_curies(
    test,
):
    """Normalize a list of curies."""
    node_norm = NODE_NORM_URL.get(test["test_env"], "")
    # collect all curies from test
    curies = set([asset["output_id"] for asset in test["test_assets"]])
    curies.update([asset["input_id"] for asset in test["test_assets"]])
    curies.add(test["test_case_input_id"])

    normalized_curies = {}
    with httpx.Client() as client:
        try:
            response = client.post(
                node_norm + "/get_normalized_nodes",
                json={
                    "curies": list(curies),
                    "conflate": True,
                    "drug_chemical_conflate": True,
                },
            )
            response.raise_for_status()
            response = response.json()
            for curie, attrs in response.items():
                if attrs is None:
                    # keep original curie
                    normalized_curies[curie] = curie
                else:
                    # choose the perferred id
                    normalized_curies[curie] = attrs["id"]["identifier"]
        except Exception as e:
            print(f"Node norm failed with: {e}")
            print("Using original curies.")
            for curie in curies:
                normalized_curies[curie] = curie
    return normalized_curies


def build_trapi_query(test_case, input_id):
    """Build a TRAPI query message from a test case definition."""
    input_category = test_case["input_category"]
    output_category = test_case["output_category"]
    predicate_id = test_case["test_case_predicate_id"]
    qualifiers = test_case.get("qualifiers", [])

    query_graph = {
        "nodes": {
            "ON": {
                "ids": [input_id],
                "categories": [input_category],
            },
            "SN": {
                "categories": [output_category],
            },
        },
        "edges": {
            "e0": {
                "subject": "SN",
                "object": "ON",
                "predicates": [predicate_id],
                "knowledge_type": "inferred",
            }
        },
    }

    # Add qualifier_constraints if qualifiers have non-empty values
    qualifier_constraints = []
    if test_case["test_case_predicate_id"] == "biolink:affects":
        for q in qualifiers:
            if q["value"]:  # skip empty qualifier values
                qualifier_constraints.append(
                    {
                        "qualifier_type_id": q["parameter"].replace("biolink_", "biolink:"),
                        "qualifier_value": q["value"],
                    }
                )
        if input_category == "biolink:ChemicalEntity":
            temp = copy.deepcopy(query_graph["nodes"]["ON"])
            query_graph["nodes"]["ON"] = copy.deepcopy(query_graph["nodes"]["SN"])
            query_graph["nodes"]["SN"] = temp

    if qualifier_constraints:
        query_graph["edges"]["e0"]["qualifier_constraints"] = [
            {"qualifier_set": qualifier_constraints}
        ]

    trapi_message = {
        "message": {
            "query_graph": query_graph,
        },
        "parameters": {
            "gandalf": True,
        }
    }

    return trapi_message


def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else "sprint_6_tests.json"
    out_file = sys.argv[2] if len(sys.argv) > 2 else "trapi_queries.json"

    with open(input_file) as f:
        data = json.load(f)

    test_cases = data["test_cases"]

    results = []

    for tc_id, tc in tqdm(test_cases.items()):
        normalized_curies = normalize_curies(tc)
        # Collect ALL assets with their expected_output type
        expected_outputs = []
        for asset in tc["test_assets"]:
            expected_outputs.append(
                {
                    "output_id": normalized_curies[asset["output_id"]],
                    "output_name": asset["output_name"],
                    "output_category": asset["output_category"],
                    "expected_output": asset["expected_output"],
                }
            )

        trapi_query = build_trapi_query(tc, normalized_curies[tc["test_case_input_id"]])

        results.append(
            {
                "test_case_id": tc_id,
                "test_case_name": tc["name"],
                "trapi_query": trapi_query,
                "expected_outputs": expected_outputs,
            }
        )

    print(f"Found {len(results)} unique TRAPI queries:\n")
    for r in results:
        by_type = {}
        for eo in r["expected_outputs"]:
            by_type.setdefault(eo["expected_output"], []).append(eo["output_name"])

        print(f"  {r['test_case_id']}: {r['test_case_name']}")
        for etype, names in by_type.items():
            print(f"    {etype} ({len(names)}): {names}")
        print()

    # Write out the queries
    output = {"queries": results}
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {len(results)} queries to {out_file}")


if __name__ == "__main__":
    main()
