# Custom Job Search Agent - Flow Diagram

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         USER INTERACTION                          │
└──────────────────────────────────────────────────────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
           ┌────────────┐  ┌─────────┐  ┌──────────┐
           │ Dashboard  │  │   CLI   │  │   API    │
           │     UI     │  │ Scripts │  │Endpoints │
           └─────┬──────┘  └────┬────┘  └────┬─────┘
                 │              │            │
                 └──────────────┼────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                    CUSTOM SEARCH AGENT                            │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  1. Load Resume from Database                              │  │
│  │  2. Parse & Extract Profile (if not cached)               │  │
│  │  3. Discover Jobs (LinkedIn, Indeed, Naukri)              │  │
│  │  4. Rank by Semantic Similarity                           │  │
│  │  5. Filter (min_score, deduplication)                     │  │
│  │  6. Save to Database                                       │  │
│  │  7. Send WhatsApp Notifications                           │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
           ┌────────────┐  ┌─────────┐  ┌──────────┐
           │  Database  │  │WhatsApp │  │ Search   │
           │  (SQLite)  │  │ Service │  │ History  │
           └────────────┘  └────┬────┘  └──────────┘
                                │
                                ▼
                        ┌──────────────┐
                        │ Twilio API   │
                        └──────┬───────┘
                               │
                               ▼
                        ┌──────────────┐
                        │User's Phone  │
                        │  (WhatsApp)  │
                        └──────────────┘
```

## Detailed Workflow

### Step 1: Resume Upload & Configuration

```
User Action: Upload Resume
         │
         ▼
┌─────────────────────┐
│  Resume Parser      │
│  - Extract text     │
│  - LLM parsing      │
│  - Store profile    │
└──────────┬──────────┘
           │
           ▼
    ┌──────────────┐
    │   Database   │
    │ Resume Table │
    │ - id         │
    │ - filename   │
    │ - profile    │
    │ - phone      │
    │ - settings   │
    └──────────────┘
```

### Step 2: One-Time Search Flow

```
User: "Search Now"
       │
       ▼
┌─────────────────────────────┐
│   Custom Search Agent       │
│                             │
│  Load Resume (id=1)         │
│  ├─ Target: "AI Engineer"  │
│  ├─ Skills: [python, ml]   │
│  └─ Experience: 2 years    │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│    Job Discovery Agent      │
│                             │
│  Parallel Scraping:         │
│  ├─ LinkedIn (15 jobs)     │
│  ├─ Indeed (15 jobs)       │
│  └─ Naukri (15 jobs)       │
└──────────┬──────────────────┘
           │
           ▼ (45 jobs)
┌─────────────────────────────┐
│   Job Ranking Agent         │
│                             │
│  Semantic Similarity:       │
│  ├─ Embed resume profile   │
│  ├─ Embed job descriptions │
│  └─ Cosine similarity      │
└──────────┬──────────────────┘
           │
           ▼ (ranked by score)
┌─────────────────────────────┐
│   Filter & Deduplicate      │
│                             │
│  ├─ Min score: 0.7         │
│  ├─ Remove duplicates      │
│  ├─ Check notification DB  │
│  └─ Top 5 matches          │
└──────────┬──────────────────┘
           │
           ▼ (5 high-match jobs)
┌─────────────────────────────┐
│   WhatsApp Service          │
│                             │
│  Format Message:            │
│  ├─ Job title & company    │
│  ├─ Match score (87%)      │
│  ├─ Location & portal      │
│  └─ Application link       │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│   Twilio API                │
│   Send via WhatsApp         │
└──────────┬──────────────────┘
           │
           ▼
    📱 User's Phone
    (Notification Received)
```

### Step 3: Scheduled Search Flow

```
User: "Schedule Daily at 9 AM"
       │
       ▼
┌─────────────────────────────┐
│   Job Search Scheduler      │
│   (APScheduler)             │
│                             │
│  Config:                    │
│  ├─ Resume ID: 1           │
│  ├─ Phone: +91xxx          │
│  ├─ Frequency: daily       │
│  ├─ Time: 09:00            │
│  └─ Min Score: 0.7         │
└──────────┬──────────────────┘
           │
           ▼
    Save to Config File
    (data/scheduler_config.json)
           │
           ▼
┌─────────────────────────────┐
│   Background Scheduler      │
│   Running in Background     │
└──────────┬──────────────────┘
           │
    Every Day at 9:00 AM
           │
           ▼
┌─────────────────────────────┐
│   Trigger Search            │
│   (Same as One-Time Flow)   │
└──────────┬──────────────────┘
           │
           ▼
    WhatsApp Notification
    📱 "Found 3 new matches!"
```

## Data Flow

### Resume Profile Data

```json
{
  "id": 1,
  "name": "john doe",
  "skills": ["python", "machine learning", "fastapi"],
  "tools": ["docker", "git", "aws"],
  "frameworks": ["langchain", "tensorflow"],
  "experience_years": "2",
  "projects": ["resume parser", "recommendation engine"],
  "preferred_roles": ["ai engineer", "ml engineer"]
}
```

### Job Discovery Data

```json
{
  "title": "Senior AI Engineer",
  "company": "TechCorp",
  "location": "Bangalore, India",
  "url": "https://linkedin.com/jobs/123",
  "portal": "linkedin",
  "description": "Build ML models with Python, TensorFlow...",
  "external_id": "linkedin-123"
}
```

### Ranking Data

```json
{
  "job": {
    "title": "Senior AI Engineer",
    "company": "TechCorp",
    "url": "https://linkedin.com/jobs/123"
  },
  "score_info": {
    "final_score": 0.87,
    "embedding_score": 0.85,
    "title_match": 1
  }
}
```

### WhatsApp Message

```
🔥 Job Match #1 (87% match)

*Senior AI Engineer*
🏢 TechCorp
📍 Bangalore, India
🌐 Portal: LinkedIn

🔗 Apply: https://linkedin.com/jobs/123

---
💼 Powered by AI Job Hunter Agent
```

### Search History Entry

```json
{
  "id": 1,
  "resume_id": 1,
  "search_type": "scheduled",
  "jobs_found": 45,
  "jobs_notified": 3,
  "location": "Bangalore",
  "min_score": 0.7,
  "portals_used": ["linkedin", "indeed"],
  "notification_sent": 1,
  "executed_at": "2024-01-15T09:00:00Z"
}
```

## State Transitions

```
┌─────────────┐
│   Initial   │  User uploads resume
│   No Resume │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Resume    │  Configure preferences
│   Uploaded  │  (phone, location, score)
└──────┬──────┘
       │
       ├─────► One-Time Search ──► Notification Sent ──► View History
       │
       └─────► Schedule Setup ──► Active Schedule ──┐
                                                     │
       ┌─────────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│  Scheduled  │  Runs automatically
│   Active    │  at configured time
└──────┬──────┘
       │
       ├─────► Search Executed ──► Jobs Found ──► Notifications Sent
       │
       └─────► No Jobs Found ──► History Logged (0 results)
```

## Component Interaction

```
┌────────────────────────────────────────────────────────────────┐
│                         Frontend Layer                          │
├────────────────────────────────────────────────────────────────┤
│  Dashboard UI  │  REST API  │  CLI Scripts  │  Demo Scripts   │
└────────┬─────────────┬──────────────┬──────────────┬───────────┘
         │             │              │              │
         └─────────────┴──────────────┴──────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
┌─────────────────┐         ┌─────────────────┐
│ Custom Search   │◄────────┤   Scheduler     │
│     Agent       │         │   (APScheduler) │
└────────┬────────┘         └─────────────────┘
         │
         ├─────► Resume Parser Agent
         ├─────► Job Discovery Agent
         ├─────► Job Ranking Agent
         └─────► WhatsApp Service
                      │
                      ▼
              ┌──────────────┐
              │  Twilio API  │
              └──────────────┘
```

## Error Handling Flow

```
Custom Search Agent
       │
       ├─► Resume Not Found ──► Return Error
       │
       ├─► Parse Failed ──► Retry / Return Error
       │
       ├─► No Jobs Found ──► Log (Success, 0 results)
       │
       ├─► Ranking Failed ──► Use Fallback (no ranking)
       │
       ├─► WhatsApp Failed ──► Log Error, Save Jobs
       │
       └─► Success ──► Log History, Return Results
```

## Performance Metrics

```
Typical Execution Time:
┌──────────────────────┬──────────┐
│ Resume Parsing       │  1-2s    │
│ Job Discovery        │  15-30s  │
│ (3 portals)          │          │
│ Job Ranking          │  2-5s    │
│ WhatsApp Send        │  1-2s    │
├──────────────────────┼──────────┤
│ Total                │  20-40s  │
└──────────────────────┴──────────┘

Database Operations:
- Resume lookup: <50ms
- Job insert: ~10ms per job
- History insert: <10ms

Notification Delivery:
- WhatsApp: 1-3s (Twilio)
- Success Rate: 99%+ (with valid credentials)
```
