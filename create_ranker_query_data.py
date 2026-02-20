import argparse
import json


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process arguments.')
    parser.add_argument('--input_file', type=str, required=False,
                        default='data/shepherd_bte_response.json',
                        help='input file of the workflow lookup response')
    parser.add_argument('--score_source', type=str, required=False,
                        default='arax',
                        help='score source: either aragorn or arax')
    parser.add_argument('--output_file', type=str, required=False,
                        default='data/bte_arax_score_query.json',
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
            "message": lookup_data['message'],
            "workflow": [
                {"id": score_id}
            ]
        }
    print(f'score_dict workflow: {score_dict["workflow"]}')
    print(f"output_file: {output_file}")
    with open(output_file, 'w') as f:
        json.dump(score_dict, f, indent=2)
    print('Done')
