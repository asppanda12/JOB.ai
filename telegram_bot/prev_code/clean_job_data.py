import json

file_path_1 = r"E:\JOB.ai\JOB.ai\Data_base\search_results_ruddhi.json"

with open(file_path_1, "r") as file:
    resume_data = json.load(file)

# Initialize as list instead of dictionary
data = []

for x in resume_data:
    # Ensure 'metadata' exists in x before accessing
    if 'metadata' in x:
        data.append(x['metadata'])

output_file = "cleaned_Ruddhis_job.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4, ensure_ascii=False)