import subprocess
from concurrent.futures import ThreadPoolExecutor
import sys
Linkedin = "E:\\JOB.ai\\JOB.ai\\Linkedin\\"
naukri = "E:\\JOB.ai\\JOB.ai\\Naukri\\"
instahyre = "E:\\JOB.ai\\JOB.ai\\Scrape_entire_web\\"
data_cleaning = "E:\\JOB.ai\\JOB.ai\\data_cleaning\\"
cuvete = "E:\\JOB.ai\\JOB.ai\\Cuvete\\"

pipeline = {
    f"{Linkedin}start_scrapping_v2_step_1.py": f"{Linkedin}drop_duplicates_linked_step_2.py",
    f"{Linkedin}drop_duplicates_linked_step_2.py": f"{Linkedin}clean_output_step3.py",
    f"{Linkedin}clean_output_step3.py": f"{Linkedin}create_json_linkedin_step4.py",
    f"{Linkedin}create_json_linkedin_step4.py": f"{data_cleaning}clean_data_linkedin.py",

    f"{naukri}start_scrapping.py": f"{naukri}create_json_naukri.py",
    f"{naukri}create_json_naukri.py": f"{data_cleaning}clean_data_naukri.py",

    f"{instahyre}instahyre_for_1yoe.py": f"{instahyre}instahyre_for_fresher.py",
    f"{instahyre}instahyre_for_fresher.py": f"{instahyre}instahyre.py",
    f"{instahyre}instahyre.py": f"{data_cleaning}clean_data_instahyre.py",

    f"{cuvete}start_scrapping.py": f"{cuvete}create_json_cuvete.py",
    f"{cuvete}create_json_cuvete.py": f"{data_cleaning}clean_data_cuvete.py",
}

# Divide into groups
groups = {
    "LinkedIn": {k:v for k,v in pipeline.items() if k.startswith(Linkedin)},
    "Naukri": {k:v for k,v in pipeline.items() if k.startswith(naukri)},
    "Instahyre": {k:v for k,v in pipeline.items() if k.startswith(instahyre)},
    "Cuvete": {k:v for k,v in pipeline.items() if k.startswith(cuvete)},
}

def run_script(script):
    """Run a Python script synchronously."""
    print(f"▶️ Running {script}")
    subprocess.run([sys.executable, script], check=True)
    print(f"✅ Finished {script}")

def run_group(group_name, sub_pipeline):
    """Run scripts of one group sequentially (parent → child)."""
    print(f"\n🚀 Starting group: {group_name}")

    # find the root (a script that is never a child)
    all_children = set(sub_pipeline.values())
    root = [s for s in sub_pipeline.keys() if s not in all_children][0]

    # walk the chain
    current = root
    while current in sub_pipeline:
        run_script(current)
        current = sub_pipeline[current]
    run_script(current)  # run last leaf

    print(f"🏁 Finished group: {group_name}\n")

def run_all_groups():
    """Run all groups in parallel."""
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(run_group, name, sub) for name, sub in groups.items()]
        for f in futures:
            f.result()

if __name__ == "__main__":
    run_all_groups()
