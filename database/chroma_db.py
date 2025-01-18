import json
import os

def concatenate_job_files():
    # List of all the file paths
    set_of_data = [
        r'E:\JOB.ai\JOB.ai\cuvete\cuevete_parsed_jobs.json',
        r'E:\JOB.ai\JOB.ai\Linkedin\linkedin_parsed_jobs.json',
        r'E:\JOB.ai\JOB.ai\naukri\naukri_parsed_jobs.json',
        r'E:\JOB.ai\JOB.ai\result_of_all_web_scraper\instahyre_jobs_1.json',
        r'E:\JOB.ai\JOB.ai\result_of_all_web_scraper\money_view_data.json'
    ]

    # List to store all concatenated job data
    all_jobs = []
    
    # Counter for successful files
    successful_files = 0

    # Iterate over each file in the list and load its contents
    for file_path in set_of_data:
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    # Assuming each file contains a list of jobs, concatenate them
                    if isinstance(data, list):
                        all_jobs.extend(data)  # Merge job listings
                        successful_files += 1
                        print(f"Successfully loaded {len(data)} jobs from {os.path.basename(file_path)}")
                    else:
                        print(f"Warning: Skipping non-list data in {file_path}")
            else:
                print(f"Warning: File not found - {file_path}")
                
        except Exception as e:
            print(f"Error loading {file_path}: {e}")

    # Create output directory if it doesn't exist
    output_file = r'E:\JOB.ai\JOB.ai\result_of_all_web_scraper\concatenated_jobs.json'
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Write the concatenated job data to a new JSON file
    try:
        with open(output_file, 'w', encoding='utf-8') as outfile:
            json.dump(all_jobs, outfile, indent=4, ensure_ascii=False)
        print(f"\nSummary:")
        print(f"- Successfully processed {successful_files} files")
        print(f"- Total jobs concatenated: {len(all_jobs)}")
        print(f"- Output saved to: {output_file}")
    except Exception as e:
        print(f"Error saving concatenated file: {e}")

if __name__ == "__main__":
    concatenate_job_files()