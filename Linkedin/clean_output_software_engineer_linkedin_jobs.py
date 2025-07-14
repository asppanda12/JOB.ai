import json
import pandas as pd

# Path to your JSON file
file_path = r"E:\JOB.ai\JOB.ai\Linkedin\_Software Engineer_India_linkedin_jobs.json"

# Reading the JSON file with UTF-8 encoding
with open(file_path, "r", encoding="utf-8") as file:
    Job_data = json.load(file)

# Convert JSON data into DataFrame
df = pd.DataFrame(Job_data)

# Drop duplicates based on 'title', 'company', and 'location' columns
df_no_duplicates = df.drop_duplicates(subset=['title', 'company', 'location'], keep='first')

# Count the rows for each column after removing duplicates
print("Row count after removing duplicates:", df_no_duplicates.count())

# Convert the DataFrame back to a JSON object
cleaned_json_data = df_no_duplicates.to_dict(orient='records')

# Save the cleaned JSON data to a new file
output_file_path = r"E:\JOB.ai\JOB.ai\Linkedin\cleaned_data.json"
with open(output_file_path, "w", encoding="utf-8") as output_file:
    json.dump(cleaned_json_data, output_file, indent=4, ensure_ascii=False)

print(f"Cleaned data saved to {output_file_path}")
