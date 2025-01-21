import json
import os

def concatenate_job_files():
    # List of all the file paths
    set_of_data = [
        r'E:\JOB.ai\JOB.ai\cleaned\cleaned_cuvete.json',
        r'E:\JOB.ai\JOB.ai\cleaned\instahyre_jobs_1.json',
        r'E:\JOB.ai\JOB.ai\cleaned\instahyre_jobs_2.json',
        r'E:\JOB.ai\JOB.ai\cleaned\instahyre_jobs_3.json',
        r'E:\JOB.ai\JOB.ai\cleaned\instahyre_jobs.json',
        r'E:\JOB.ai\JOB.ai\cleaned\linkedin.json',
        r'E:\JOB.ai\JOB.ai\cleaned\naukri.json',
    ]

    all_jobs = []
    successful_files = 0

    # Try different encodings if one fails
    encodings = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252']

    for file_path in set_of_data:
        if os.path.exists(file_path):
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as file:
                        data = json.load(file)
                        if isinstance(data, list):
                            all_jobs.extend(data)
                            successful_files += 1
                            print(f"Successfully loaded {len(data)} jobs from {os.path.basename(file_path)} using {encoding}")
                            break  # Break the encoding loop if successful
                        else:
                            print(f"Warning: Skipping non-list data in {file_path}")
                            break
                except UnicodeDecodeError:
                    print(f"Failed to decode {file_path} with {encoding}, trying next encoding...")
                    continue  # Try next encoding
                except json.JSONDecodeError as e:
                    print(f"JSON decode error in {file_path}: {e}")
                    break  # Break if JSON is invalid
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")
                    break
        else:
            print(f"Warning: File not found - {file_path}")

    # Create output directory if it doesn't exist
    output_file = r'E:\JOB.ai\JOB.ai\combined_single_data\concatenated_jobs.json'
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

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
