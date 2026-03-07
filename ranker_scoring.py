import argparse
import json
import requests

headers = {
    "accept": "application/json",
    "Content-Type": "application/json"
}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process arguments.')
    parser.add_argument('--input_file', type=str, required=False,
                        default='data/arax_arax_score_query_no_direct_edges.json',
                        help='input file of the workflow lookup response')
    parser.add_argument('--ranker', type=str, required=False,
                        default='arax',
                        help='input ranker, supported rankers are aragorn and arax')
    parser.add_argument('--output_file', type=str, required=False,
                        default='results/shepherd_arax_arax_score_response_no_direct_edges.json',
                        help='output file for the scored response')

    args = parser.parse_args()
    input_file = args.input_file
    output_file = args.output_file
    ranker = args.ranker

    # Read request body from JSON file
    with open(input_file, "r") as f:
        data = json.load(f)

    if ranker == 'aragorn':
        url = "https://shepherd.renci.org/aragorn/query"
    elif ranker == 'arax':
        url = "https://shepherd.renci.org/arax/query"
    else:
        print(f'invalid input ranker {ranker}. Supported input rankers are aragorn and arax')
        exit(1)

    # Send POST request
    response = requests.post(url, headers=headers, json=data)

    # Raise exception if request failed
    response.raise_for_status()

    # Write response to file
    with open(output_file, "w") as f:
        json.dump(response.json(), f, indent=2)

    print(f"Response saved to {output_file}")
    exit(0)
