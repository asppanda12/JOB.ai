from selenium import webdriver
from selenium.webdriver.common.keys import Keys
import time
from bs4 import BeautifulSoup 
import requests 
from selenium.webdriver.common.by import By
import csv

class get_remote_driver:
    def getHTMLdocument(self,url): 
        response = requests.get(url) 
        return response.text 

    def __init__(self):
        options = webdriver.ChromeOptions()
        options.add_argument('disable-infobars')
        options.add_argument('start-maximized')
        options.add_argument('disable-dev-shm-usage')
        options.add_argument('no-sandbox')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_argument("disable-blink-feature=AutomationControlled")
        driver = webdriver.Chrome(options=options)
        
        driver.get("https://cuvette.tech/app/dashboard/other-jobs")
        time.sleep(15)
        self.driver=driver
    def data_extraction(self):
        root = self.driver.find_element(By.XPATH, '/html/body/div[1]/div[4]/div/div[1]/div/div/div[2]')
        header = root.find_elements(By.XPATH, "./div")
        div_elements=header[0].find_elements(By.XPATH, "./div")

        num_divs = len(div_elements)

        # header=root.find_element(By.XPATH,'//*[@id="root"]/div[4]/div[2]/div[1]/div/div/div[2]')
        # bottom=header.find_element(By.XPATH,'/html/body/div[1]/div[4]/div[2]/div[1]/div/div/div[2]/div')
        # inner=bottom.find_element(By.XPATH,"/html/body/div[1]/div[4]/div[2]/div[1]/div/div/div[2]/div/div[1]/div[1]/div[1]/div[1]/div/div[1]")
        # inside_most=inner.find_element(By.CLASS_NAME,'.OtherJobsCard_lightText__12EQI OtherJobsCard_darkText__356ok')
        
        return div_elements
    def quit_driver(self):
        self.driver.quit()
try:
    val = get_remote_driver()
    header=val.data_extraction()
    # OtherJobsCard_lightText__12EQI OtherJobsCard_darkText__356ok
    output_filename = 'output.txt'
    # text_content = header[0].get_attribute('outerHTML')
    valp=[]
    for div in header:
        lst=div.text.split('\n')
        al_val=lst[:-4]
        valp.append(al_val)
    # print(valp)

    columns = ['Company Name', 'Job Title', 'Location', 'Skills', 'Job Type', 'Salary', 'Experience']
    final_output=[]
    for x in valp:
        company_name=x[0]
        Job_Title=x[1]
        Location=x[2]
        Skills=x[3:-3]
        job_type=x[-3]
        # salary=x[-2].split(":")[1]
        salary=x[-2]
        # yoe=(" ").join(x[-1].split("-")[1:])
        yoe=x[-1]
        lst=[company_name,Job_Title,Location,Skills,job_type,salary,yoe]
        final_output.append(lst)

    filename = 'finale_jobs.csv'

    # Write data to CSV file
    with open(filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write the header
        writer.writerow(columns)
        
        # Write the rows
        writer.writerows(final_output)

    print("done")
    val.quit_driver()
except:
    print("error occured")
    val.quit_driver()