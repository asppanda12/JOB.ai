"""Prompt templates. Kept together so wording changes are reviewable in one place."""

from __future__ import annotations

SYSTEM_EXTRACTOR = (
    "You are a precise information extraction engine. You output only valid JSON "
    "matching the requested schema. You never invent facts that are not present "
    "in the input; use null or an empty list when something is absent."
)

SYSTEM_WRITER = (
    "You are an experienced technical recruiter and career coach. You write "
    "concise, specific, professional prose. You never invent employers, degrees, "
    "dates or achievements that are not in the candidate's resume."
)

RESUME_PROFILE = """Extract a structured candidate profile from the resume text below.

Return JSON with exactly these keys:
{{
  "name": string or null,
  "email": string or null,
  "phone": string or null,
  "target_roles": [string],        // roles this person is a fit for, e.g. "Machine Learning Engineer"
  "skills": [string],              // all technical skills
  "languages": [string],           // programming languages only
  "frameworks": [string],          // libraries and frameworks
  "cloud": [string],               // cloud platforms and infra tooling
  "databases": [string],
  "years_experience": number,      // total professional years, 0 for a fresher
  "industries": [string],
  "preferred_locations": [string],
  "remote_preference": "remote" | "hybrid" | "onsite" | null,
  "education": [{{"institution": string, "degree": string, "year": string or null}}],
  "projects": [{{"name": string, "description": string, "technologies": [string]}}],
  "experience": [{{"company": string, "position": string, "duration": string,
                   "achievements": [string], "technologies": [string]}}]
}}

Rules:
- Use the exact skill spelling that appears in the resume; do not expand or abbreviate.
- years_experience counts professional work only, excluding internships shorter than 6 months.
- Omit nothing: every key must be present, using [] or null when unknown.

Resume text:
{resume_text}
"""

JOB_UNDERSTANDING = """Read the job posting below and extract its structured requirements.

Return JSON with exactly these keys:
{{
  "required_skills": [string],   // skills the posting states as mandatory
  "preferred_skills": [string],  // "nice to have", "bonus", "preferred"
  "job_category": string,        // e.g. "Backend Engineer", "Data Scientist", "MLOps Engineer"
  "industry": string or null,
  "employment_type": string or null,   // full-time, contract, internship
  "remote": true | false | null,
  "education": [string],
  "experience_min_years": number or null,
  "experience_max_years": number or null
}}

Only use what the posting actually says.

Job posting:
{job_text}
"""

QUERY_EXPANSION = """A job seeker searched for: "{query}"

List the technologies, frameworks and role titles that postings for this kind of
work typically mention. Stay strictly within the same field - do not drift into
adjacent professions.

Return JSON: {{"expansions": [string], "role_titles": [string]}}
Give at most 12 expansions and at most 5 role titles.
"""

MATCH_REASONING = """You are explaining job recommendations to a candidate.

Candidate profile:
{profile}

For each job below you are given pre-computed match signals. Use them; do not
re-rank the jobs and do not change their order.

{jobs}

Return JSON: {{"recommendations": [{{"job_id": string, "verdict": string,
"reasons": [string], "missing_skills": [string], "how_to_prepare": string}}]}}

- "verdict" is one short sentence on why this job fits (or where it falls short).
- "reasons" is 2-4 short bullet phrases grounded in the signals given.
- "missing_skills" comes from the gap data provided; [] when there is no gap.
- "how_to_prepare" is one actionable sentence.
"""

SKILL_GAP = """Candidate skills: {user_skills}
Skills required across the jobs they are targeting: {job_skills}

Return JSON: {{"missing_critical": [string], "missing_nice_to_have": [string],
"transferable": [{{"has": string, "covers": string}}], "advice": string}}

"transferable" lists cases where a skill the candidate already has meaningfully
covers a skill they lack. "advice" is two sentences at most.
"""

COVER_LETTER = """Write a cover letter email for this application.

Candidate profile (JSON):
{profile}

Job:
{job}

Requirements:
- Open with a specific greeting, not "To whom it may concern" unless no name is known.
- Say plainly why this candidate fits THIS role, citing concrete work from the resume.
- Connect their skills to the job's stated requirements.
- Close by asking for a conversation.
- Plain text, no markdown, under 3500 characters.
Return only the email body.
"""

REFERRAL_MESSAGE = """Write a short LinkedIn message asking a current employee for a referral.

Candidate profile (JSON):
{profile}

Job:
{job}

Requirements:
- Polite greeting, one-line self introduction.
- State interest in this specific role and give one concrete reason they are a fit.
- Ask directly but politely whether they would be open to referring.
- Under 900 characters. Plain text, no markdown.
Return only the message.
"""

COLD_EMAIL = """Write a cold email to a hiring manager about this role.

Candidate profile (JSON):
{profile}

Job:
{job}

Requirements:
- Subject line on the first line, prefixed "Subject: ".
- Two or three short paragraphs: who they are, why this role, what they bring.
- Cite specific achievements from the resume, with numbers where the resume has them.
- End with a clear call to action.
- Plain text, no markdown, under 3500 characters.
Return only the email.
"""
