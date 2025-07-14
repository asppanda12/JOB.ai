from pydantic import BaseModel, EmailStr
from pydantic_extra_types.phone_numbers import PhoneNumber
from typing import Dict, Any
from typing import List
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime

# Define User Schema with Phone Number Validation
class User(BaseModel):
    chat_id: int
    full_name: str
    years_of_experience: float
    email: EmailStr
    phone_number: str  # Automatic phone number validation
    resume_json: Dict[str, Any]

class JobSchema:
    def __init__(self, job_title="N/A", job_link="N/A", company_name="N/A", experience="N/A", salary="N/A",
                 location="N/A", job_description="N/A", years_of_experience="N/A", skills="N/A", job_type="N/A",
                 id="N/A", text="N/A", Posted_date=None, Source="N/A", yoe=None,indx=0):
        
        self.job_title = job_title
        self.job_link = str(job_link)  # Ensure it's stored as a string
        self.company_name = company_name
        self.experience = experience
        self.salary = salary
        self.location = location
        self.job_description = job_description
        self.years_of_experience = years_of_experience
        self.skills = skills
        self.job_type = job_type
        self.id = id
        self.text = text
        self.Posted_date = Posted_date
        self.Source = Source
        self.yoe = yoe if isinstance(yoe, list) else []
        self.job_indx=indx

    def to_dict(self):
        """Convert the object to a dictionary for MongoDB insertion."""
        return {
            "job_title": self.job_title,
            "job_link": self.job_link,
            "company_name": self.company_name,
            "experience": self.experience,
            "salary": self.salary,
            "location": self.location,
            "job_description": self.job_description,
            "years_of_experience": self.years_of_experience,
            "skills": self.skills,
            "job_type": self.job_type,
            "id": self.id,
            "text": self.text,
            "Posted_date": self.Posted_date.strftime("%Y-%m-%d") if self.Posted_date else None,
            "Source": self.Source,
            "yoe": self.yoe,
            "indx":self.job_indx
        }




# # Corrected User Data
# user_data = User(
#     chat_id="1243",  # chat_id should be a string
#     full_name="Sameer Kumar Panda",
#     years_of_experience=1.5,
#     email="sameer@example.com",  # Email is required
#     phone_number="+919102292779",  # Phone number in international format
#     resume_json={"ho": "hi", "pada": "kon"}  # JSON field
# )

# print(user_data.dict())  # Print validated user data
# job_data = {
#     "job_title": "Software Engineer",
#     "job_link": "https://example.com/job",
#     "company_name": "Google",
#     "experience": "2-5 years",
#     "salary": "Rs. 10 LPA - Rs. 15 LPA",
#     "location": "Bangalore",
#     "job_description": "Backend Developer Role",
#     "years_of_experience": "2-5",
#     "skills": "Python, Django, SQL",
#     "job_type": "Backend Engineer",
#     "id": "Software Engineer Google 2-5 years Bangalore",
#     "text": "Software Engineer Google Python, Django, SQL Bangalore",
#     "Posted_date": datetime.strptime("2025-01-20", "%Y-%m-%d").date(),
#     "Source": "LinkedIn",
#     "yoe": [2, 5]
# }

# job_obj = JobSchema(**job_data)
# print(job_obj.to_dict())  # Convert to dict for MongoDB insertion
