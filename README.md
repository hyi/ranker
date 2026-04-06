## Performance Comparison of ARAGORN and ARAX Rankers  

This repo includes scripts for performance comparison of ARAGORN and ARAX rankers
to the lookup results from three ARAs---ARAGORN, ARAX, and BTE ARAs.

## Installation and Environment Setup for running the comparison pipeline

- Create a virtual environment and install pandas library
- Run the script below to take a json input file that includes a list of test queries to be sent to the three ARAs for 
lookup and ranking, and output an Excel workbook that includes ranker comparisons. Direct edges will be filtered out 
from the loopup results from each of the three ARAs before sending lookup results to the two rankers for ranking so 
that only derived lookup results will be included for ranking performance comparison. 
- 
```angular2html
python run_pipeline.py --input_file <input_json_file_of_list_of_test_queries> --out_file <ranker_comparison_output_file_in_excel>
```
