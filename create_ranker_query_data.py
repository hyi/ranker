import argparse
import json



def main():
    parser = argparse.ArgumentParser(description='Process arguments.')
    parser.add_argument('--input_file', type=str, required=False,
                        default='data/shepherd_aragorn_response.json',
                        help='input file of the workflow lookup response')
    parser.add_argument('--output_file', type=str, required=False,
                        default='data/aragorn_score_query.json',
                        help='output file for the score query formed from input file')

    args = parser.parse_args()
    input_file = args.input_file
    output_file = args.output_file


    with open(input_file, 'r') as f:
        lookup_data = json.load(f)

    score_dict = {
            "message": lookup_data['message'],
            "workflow": [
                {"id": "aragorn.score"}
            ]
        }

    with open(output_file, 'w') as f:
        json.dump(score_dict, f, indent=2)
