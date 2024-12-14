from pyresparser import ResumeParser

try:
    data = ResumeParser(r'E:\\JOB.ai\\JOB.ai\\job_resume\\ruddhi_7748640302.pdf').get_extracted_data()
    print(data)
except FileNotFoundError as e:
    print("File not found:", e)
except Exception as e:
    print("An error occurred:", e)
