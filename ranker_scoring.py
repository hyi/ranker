import argparse
import json
import requests

headers = {
    "accept": "application/json",
    "Content-Type": "application/json"
}

URL = "https://shepherd.renci.org/aragorn/query"

def run_query(payload):
    r = requests.post(URL, headers=headers, json=payload)

    try:
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"status code: {r.status_code}, HTTP error occurred: {e}")
        return None

    return r.json()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process arguments.')
    parser.add_argument('--input_file', type=str, required=False,
                        default='data/query3/aragorn_arax_score_query_no_direct_edges.json',
                        help='input file of the workflow lookup response')
    parser.add_argument('--output_file', type=str, required=False,
                        default='results/query3/shepherd_aragorn_arax_score_response_no_direct_edges.json',
                        help='output file for the scored response')

    args = parser.parse_args()
    input_file = args.input_file
    output_file = args.output_file

    # Read request body from JSON file
    with open(input_file, "r") as f:
        data = json.load(f)

    resp_json = run_query(data)

    if resp_json:
        with open(output_file, "w") as f:
            json.dump(resp_json, f, indent=2)
        print(f"Response saved to {output_file}")
    else:
        print(f'no valid response is returned for the query in {input_file}')
    exit(0)
