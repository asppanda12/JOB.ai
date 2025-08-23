import json
import re
# nltk.download('stopwords')
# nltk.download('punkt_tab')
def replace_asterisks(data):
    cleaned_data = []
    for item in data:
        cleaned_item = {}
        for key, value in item.items():
            if isinstance(value, str):
                # Replace all asterisks with a single space
                value = re.sub(r'\*+', ' ', value)
            cleaned_item[key] = value
        cleaned_data.append(cleaned_item)
    return cleaned_data
# Read JSON file
def read_json_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data

# Example usage
file_path = r'All_Companies_Software Engineer_India_linkedin_jobs.json'
data = read_json_file(file_path)

# Print the data (optional)
json_response = replace_asterisks(data)
print(len(json_response))
# Specify the file path where you want to save the cleaned data
file_path = "cleaned_data_sde.json"

# Write the cleaned data to the specified JSON file
try:
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(json_response, f, indent=4, ensure_ascii=False)  # Write the cleaned data
    print(f"Data has been successfully written to {file_path}")
except Exception as e:
    print(f"Error writing to file: {e}")
