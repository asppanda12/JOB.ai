# JOB.ai

## Overview

JOB.ai is an automated job aggregation and recommendation platform designed to streamline the job search and application process. It scrapes job listings from multiple sources, cleans and merges the data, builds a semantic vector database for efficient search, and interacts with users via a Telegram bot to deliver personalized job recommendations and application support.

---

https://github.com/user-attachments/assets/2710f98f-7da0-4ffd-a5e9-6dcf949f2810



## Architecture & Workflow

The JOB.ai system is modular and highly automated. Below is a detailed breakdown of each stage in the workflow:

### 1. Scraping Job Data (Parallel Execution)

**Sources:**
- **Linkedin**
- **Cuvete**
- **Naukri**
- **Instahyre & Entire Web**




**Process:**
- Each source has its own scraping script (`start_scrapping.py`) that collects raw job data.
- The raw data is converted to JSON format for consistency (`create_json_*.py`).
- Data cleaning scripts (`data_cleaning/cleaned_data_*.py`) standardize and sanitize the job listings, removing duplicates and formatting fields.

**Parallelization:**  
All scrapers can be run simultaneously to maximize throughput and minimize latency.

---

### 2. Data Combination

- The cleaned datasets from all sources are merged using `combined_single_data/master_data.py`.
- This step ensures a unified schema and removes any remaining duplicates.
- The master data file imports and utilizes helper scripts for efficient merging and transformation.

---

### 3. Semantic Vector Database

- The merged dataset is indexed using FAISS (`Data_base/faiss_db_v2.py`), a high-performance vector database.
- This enables fast, semantic search and matching of jobs to user profiles and queries.

---

### 4. Telegram Bot Interaction

- The Telegram bot (`telegram_bot/telegram_bot.py`) is the user-facing component.
- **Registration:** Users provide their name, phone, email, years of experience, and upload their CV (PDF).
- **Job Recommendations:** The bot sends jobs in batches, with a "Send More Jobs" button for pagination.
- **Application Support:** For each job, users can request:
  - Referral mail
  - Cover letter
  - Cold email template
- **Data Storage:** All user data and job recommendations are stored in MongoDB for persistence and analytics.

---

## Workflow Diagram

```mermaid
flowchart TD
    subgraph Scraping
        A1[Linkedin/start_scrapping.py]
        A2[Linkedin/create_json_linkedin.py]
        A3[data_cleaning/cleaned_data_linkedin.py]

        B1[cuvete/start_scrapping.py]
        B2[cuvete/create_json_cuvete.py]
        B3[data_cleaning/cleaned_data_cuvete.py]

        C1[naukri/start_scrapping.py]
        C2[naukri/create_json_naukri.py]
        C3[data_cleaning/cleaned_data_naukri.py]

        D1[Scrape_entire_web/instahyre_1yoe.py]
        D2[Scrape_entire_web/Instahyre_for_fresher.py]
        D3[Scrape_entire_web/instahyre.py]
        D4[data_cleaning/cleaned_data_for_instahyre.py]
    end

    subgraph Data Combination
        E1[combined_single_data/master_data.py]
    end

    subgraph Vector DB
        F1[Data_base/faiss_db_v2.py]
    end

    subgraph Telegram Bot
        G1[telegram_bot/telegram_bot.py]
        G2[User Registration]
        G3[Job Recommendation]
        G4[Referral/CL/Cold Email Generation]
    end

    %% Scraping flows
    A1 --> A2 --> A3 --> E1
    B1 --> B2 --> B3 --> E1
    C1 --> C2 --> C3 --> E1
    D1 --> D4 --> E1
    D2 --> D4 --> E1
    D3 --> D4 --> E1

    %% Data Combination to Vector DB
    E1 --> F1

    %% Vector DB to Telegram Bot
    F1 --> G1

    %% Telegram Bot workflow
    G1 --> G2
    G2 --> G3
    G3 --> G4
```

---

## Telegram Bot Features

- **User Registration:** Collects user details and CV for personalized recommendations.
- **Job Recommendations:** Sends jobs in batches, supports pagination.
- **Application Support:** Generates referral mails, cover letters, and cold emails tailored to each job.
- **Persistence:** All user interactions and recommendations are stored in MongoDB.

---

## Setup Instructions

1. **Clone the repository** and navigate to the project directory.
2. **Install dependencies**:
    ```sh
    pip install -r requirements.txt
    ```
3. **Set up environment variables** in `.env`:
    ```
    TOKEN=your_telegram_bot_token
    MONGO_DB_URI=your_mongodb_uri
    ```
4. **Run the workflow steps** as described above.

---

## File Structure

- `Linkedin/`, `cuvete/`, `naukri/`, `Scrape_entire_web/`: Scrapers and raw data.
- `data_cleaning/`: Data cleaning scripts.
- `combined_single_data/`: Data merging scripts.
- `Data_base/`: Database and vector store scripts.
- `telegram_bot/`: Telegram bot source code.
- `resume_cold_mail/`: Resume parsing and mail generation.

---

## Notes

- Ensure MongoDB is running and accessible.
- The Telegram bot requires a valid bot token.
- All scripts should be run in the specified order for correct data flow.
- For production, consider using process managers (e.g., supervisord, systemd) and Docker for deployment.

---

## License

See [LICENSE](LICENSE) for details.
