import json
file_path_1 = r"E:\JOB.ai\JOB.ai\Data_base\search_results.json"


with open(file_path_1, "r") as file:
    resume_data = json.load(file)

print(resume_data)