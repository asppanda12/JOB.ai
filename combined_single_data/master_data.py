import json
import os
import sys
sys.path.append('E:/JOB.ai/JOB.ai')  
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from typing import List
from Data_base.mongodb import create_a_job_database
from Data_base.schema_for_mongo_db import JobSchema

# Load environment variables
load_dotenv()
uri = os.getenv("MONGO_DB_URI")

# Add project path for module imports
sys.path.append("E:/JOB.ai/JOB.ai")

def delete_results_for_chat_id(data_base):
        result = data_base.delete_many({})  # Delete all matching documents
        print(f"Deleted {result.deleted_count}")
def concatenate_job_files():
    """
    Reads job data from multiple JSON files, merges them into a single list,
    stores the data in MongoDB, and saves a concatenated JSON file.
    """
    # List of job data file paths
    job_files = [
        r"E:\JOB.ai\JOB.ai\cleaned\cleaned_cuvete.json",
        r"E:\JOB.ai\JOB.ai\cleaned\instahyre_jobs_1.json",
        r"E:\JOB.ai\JOB.ai\cleaned\instahyre_jobs_2.json",
        r"E:\JOB.ai\JOB.ai\cleaned\instahyre_jobs_3.json",
        r"E:\JOB.ai\JOB.ai\cleaned\instahyre_jobs.json",
        r"E:\JOB.ai\JOB.ai\cleaned\linkedin.json",
        r"E:\JOB.ai\JOB.ai\cleaned\naukri.json",
    ]

    all_jobs = []
    successful_files = 0
    encodings = ["utf-8", "utf-8-sig", "latin1", "cp1252"]

    # Read and load job data from files
    for file_path in job_files:
        if not os.path.exists(file_path):
            print(f"⚠️ Warning: File not found - {file_path}")
            continue

        for encoding in encodings:
            try:
                with open(file_path, "r", encoding=encoding) as file:
                    data = json.load(file)

                    if isinstance(data, list):
                        all_jobs.extend(data)
                        successful_files += 1
                        print(f"✅ Successfully loaded {len(data)} jobs from {os.path.basename(file_path)} using {encoding}")
                    else:
                        print(f"⚠️ Skipping non-list data in {file_path}")

                    break  # Stop checking other encodings if successful
            except UnicodeDecodeError:
                print(f"❌ Failed to decode {file_path} with {encoding}, trying next encoding...")
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error in {file_path}: {e}")
                break
            except Exception as e:
                print(f"❌ Error loading {file_path}: {e}")
                break

    # Connect to MongoDB
    db = create_a_job_database(uri)
    delete_results_for_chat_id(db,)
    # Insert data into MongoDB
    for idx,data in enumerate(all_jobs):
        try:
            user_data = {
            "job_title": data.get("job_title", "N/A"),
            "job_link": str(data.get("job_link", "N/A")),  # Ensure URL is a string
            "company_name": data.get("company_name", "N/A"),
            "experience": data.get("experience", "N/A"),
            "salary": data.get("salary", "N/A"),
            "location": data.get("location", "N/A"),
            "job_description": data.get("job_description", "N/A"),
            "years_of_experience": str(data.get("years_of_experience", "N/A")),  # Ensure string format
            "skills": data.get("skills", "N/A"),
            "job_type": data.get("job_type", "N/A"),
            "id": data.get("id", "N/A"),
            "text": data.get("text", "N/A"),
            "Posted_date": datetime.strptime(data["Posted_date"], "%Y-%m-%d") if data.get("Posted_date") else None,
            "Source": data.get("Source", "N/A"),
            "yoe": data.get("yoe", []),
            "job_indx":idx
        }

            db.insert_one(user_data)  # Insert dictionary into MongoDB
        except Exception as e:
            print(f"❌ Error inserting data into MongoDB: {e}")

    # Save concatenated data to a JSON file
    output_file = r"E:\JOB.ai\JOB.ai\combined_single_data\concatenated_jobs.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    try:
        with open(output_file, "w", encoding="utf-8") as outfile:
            json.dump(all_jobs, outfile, indent=4, ensure_ascii=False)

        print("\n📌 Summary:")
        print(f"✅ Successfully processed {successful_files} files")
        print(f"✅ Total jobs concatenated: {len(all_jobs)}")
        print(f"✅ Output saved to: {output_file}")
    except Exception as e:
        print(f"❌ Error saving concatenated file: {e}")


if __name__ == "__main__":
    concatenate_job_files()
