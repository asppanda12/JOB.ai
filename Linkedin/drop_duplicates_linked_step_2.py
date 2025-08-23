import json
import pandas as pd  # Import pandas for Excel/JSON handling

file_paths = [
    'All_Companies_AI Engineer_India_linkedin_jobs.json',
    'All_Companies_Software Engineer_India_linkedin_jobs.json',
    'All_Companies_Data Scientist Machine Learning Engineer_India_linkedin_jobs.json'
]
output_file = r"E:\JOB.ai\JOB.ai\Linkedin\Cleaned_json_data\merged_data.json"

all_data = []

# Load all JSON files into a single list
for file in file_paths:
    with open(file, "r", encoding="utf-8") as f:
        all_data.extend(json.load(f))

# Convert into DataFrame
df = pd.DataFrame(all_data)

# Drop duplicates (if job postings repeat across files)
print(len(df))
df = df.drop_duplicates()
print(len(df))

# Save as JSON
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(df.to_dict(orient="records"), f, indent=4)

print(f"✅ Merged {len(file_paths)} files into one JSON with {len(df)} unique records.")
