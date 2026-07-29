# Custom Job Search with WhatsApp Notifications

## Overview

The **Custom Job Search Agent** is an autonomous AI agent that automatically searches for jobs based on your resume and sends WhatsApp notifications for high-match opportunities.

## Features

### 🤖 Autonomous Job Hunting
- Upload your resume once
- AI automatically extracts your skills and preferences
- Searches multiple job portals (LinkedIn, Indeed, Naukri)
- Ranks jobs by semantic similarity to your profile

### 📱 WhatsApp Notifications
- Instant notifications for high-match jobs
- Formatted messages with job details and links
- Click to apply directly from WhatsApp
- No email clutter - get alerts on your phone

### ⏰ Scheduled Searches
- Set it and forget it
- Hourly, daily, or weekly searches
- Configurable time preferences
- Automatic deduplication (no repeat notifications)

### 📊 Search History
- Track all searches and results
- View notification history
- Analyze job discovery patterns

## Quick Start

### 1. Setup WhatsApp Notifications (Twilio)

Get your Twilio credentials:
1. Sign up at [twilio.com](https://www.twilio.com)
2. Get your Account SID and Auth Token
3. Enable WhatsApp sandbox: [console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn)
4. Send "join <your-sandbox-name>" to the Twilio WhatsApp number

Add to your `.env` file:
```bash
TWILIO_ACCOUNT_SID=your_account_sid_here
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_NUMBER=+14155238886  # Your Twilio WhatsApp number
```

### 2. Upload Your Resume

**Via Dashboard:**
```bash
python main.py dashboard
```
Navigate to "Custom Search" tab → Upload resume with WhatsApp number

**Via API:**
```bash
curl -X POST http://localhost:8000/api/upload-resume \
  -F "file=@resume.pdf"
```

### 3. Run a Search

**Option A: One-Time Search (Dashboard)**
1. Open dashboard → Custom Search tab
2. Configure search preferences
3. Click "Search & Notify Now"
4. Check WhatsApp for notifications

**Option B: Schedule Periodic Search (Dashboard)**
1. Open dashboard → Scheduled Search tab
2. Set frequency (hourly, daily, weekly)
3. Click "Activate Scheduled Search"
4. Sit back and receive automatic notifications

**Option C: CLI**
```bash
# One-time search
python agents/custom_search_agent.py <resume_id> +919876543210 "Bangalore"

# Schedule daily search at 9 AM
python notifications/scheduler.py add 1 +919876543210 --frequency daily --hour 9

# List scheduled searches
python notifications/scheduler.py list

# Start scheduler daemon
python notifications/scheduler.py start
```

**Option D: API**
```bash
# One-time custom search
curl -X POST http://localhost:8000/api/custom-search \
  -H "Content-Type: application/json" \
  -d '{
    "resume_id": 1,
    "user_phone": "+919876543210",
    "location": "Bangalore",
    "min_score": 0.7,
    "max_jobs_per_search": 5,
    "portals": ["linkedin", "indeed"]
  }'

# Schedule periodic search
curl -X POST http://localhost:8000/api/schedule-search \
  -H "Content-Type: application/json" \
  -d '{
    "resume_id": 1,
    "user_phone": "+919876543210",
    "frequency": "daily",
    "hour": 9,
    "minute": 0,
    "min_score": 0.7,
    "max_jobs_per_search": 5
  }'

# Remove scheduled search
curl -X DELETE http://localhost:8000/api/schedule-search/1

# List scheduled searches
curl http://localhost:8000/api/scheduled-searches
```

## Configuration

### Search Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resume_id` | int | required | Database ID of your resume |
| `user_phone` | string | required | WhatsApp number (+country_code + number) |
| `location` | string | None | Location filter (e.g., "Bangalore", "Remote") |
| `min_score` | float | 0.7 | Minimum match score (0-1) |
| `max_jobs_per_search` | int | 5 | Max jobs to notify per search |
| `portals` | list | all | Job portals: ["linkedin", "indeed", "naukri"] |

### Scheduling Options

| Frequency | Description | Example |
|-----------|-------------|---------|
| `hourly` | Every hour | Every 60 minutes |
| `every_4h` | Every 4 hours | 4-hour intervals |
| `every_12h` | Every 12 hours | Twice daily |
| `daily` | Once per day | Every day at specified time |
| `weekly` | Once per week | Every Monday at specified time |

### Phone Number Format

**Correct formats:**
- `+919876543210` (India)
- `+12025551234` (USA)
- `+447700123456` (UK)

**Incorrect formats:**
- `9876543210` (missing country code)
- `+91 98765 43210` (spaces not allowed)
- `+91-9876543210` (hyphens not allowed)

## How It Works

### 1. Resume Parsing
```python
# Extract structured data from resume
{
  "name": "John Doe",
  "skills": ["python", "machine learning", "fastapi"],
  "experience_years": "2",
  "preferred_roles": ["AI Engineer", "ML Engineer"]
}
```

### 2. Job Discovery
```python
# Search multiple portals
jobs = discover_jobs(
    target_role="AI Engineer",
    location="Bangalore",
    portals=["linkedin", "indeed", "naukri"]
)
```

### 3. Semantic Ranking
```python
# Rank by similarity to resume
ranked = rank_jobs(
    jobs=jobs,
    candidate_profile=resume_profile,
    min_score=0.7  # Only jobs above 70% match
)
```

### 4. WhatsApp Notification
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

## Architecture

```
┌─────────────────┐
│  User uploads   │
│     resume      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Resume Parser   │  ◄─── OpenAI GPT
│ (LLM Agent)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Custom Search   │
│     Agent       │
└────────┬────────┘
         │
         ├──► Job Discovery (Playwright scrapers)
         │
         ├──► Semantic Ranking (embeddings + cosine similarity)
         │
         ├──► Deduplication (URL-based)
         │
         └──► WhatsApp Service (Twilio)
                      │
                      ▼
              ┌──────────────┐
              │  User Phone  │
              └──────────────┘
```

## API Endpoints

### Upload Resume
```http
POST /api/upload-resume
Content-Type: multipart/form-data

file: resume.pdf
```

### Run Custom Search
```http
POST /api/custom-search
Content-Type: application/json

{
  "resume_id": 1,
  "user_phone": "+919876543210",
  "location": "Bangalore",
  "min_score": 0.7,
  "max_jobs_per_search": 5,
  "portals": ["linkedin", "indeed"]
}
```

### Schedule Search
```http
POST /api/schedule-search
Content-Type: application/json

{
  "resume_id": 1,
  "user_phone": "+919876543210",
  "frequency": "daily",
  "hour": 9,
  "minute": 0,
  "min_score": 0.7
}
```

### List Scheduled Searches
```http
GET /api/scheduled-searches
```

### Remove Scheduled Search
```http
DELETE /api/schedule-search/{resume_id}
```

### List Resumes
```http
GET /api/resumes
```

## Troubleshooting

### No WhatsApp Messages Received

**Check:**
1. Twilio credentials in `.env` are correct
2. WhatsApp sandbox is activated (send "join" message)
3. Phone number format is correct (+country_code + number)
4. Check logs for Twilio errors

**Test manually:**
```python
from notifications.whatsapp_service import send_whatsapp_notification

result = send_whatsapp_notification(
    phone_number="+919876543210",
    message="Test message"
)
print(result)
```

### Scheduler Not Running

**Start manually:**
```bash
python notifications/scheduler.py start
```

**Or via Python:**
```python
from notifications.scheduler import get_scheduler

scheduler = get_scheduler()
scheduler.start()
```

### No Jobs Found

**Possible causes:**
1. No jobs match your criteria on portals
2. Min score too high (try 0.6 instead of 0.7)
3. Location filter too restrictive
4. Scrapers failing (check logs)

**Test scrapers:**
```python
from agents.job_discovery_agent import discover_jobs

jobs = discover_jobs(
    target_role="AI Engineer",
    location=None,  # Try without location
    portals=["linkedin"],
    max_per_portal=10
)
print(f"Found {len(jobs)} jobs")
```

### Database Issues

**Reset database:**
```bash
rm data/job_hunter.db
python -c "from database.db import init_db; init_db()"
```

## Production Deployment

### Using Twilio Production (Not Sandbox)

1. Upgrade to paid Twilio account
2. Request WhatsApp Business API access
3. Get approved WhatsApp template messages
4. Update `.env` with production credentials

### Running as Background Service

**Using systemd (Linux):**

Create `/etc/systemd/system/job-hunter-scheduler.service`:
```ini
[Unit]
Description=AI Job Hunter Scheduler
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/ai_job_hunter_agent
ExecStart=/path/to/venv/bin/python notifications/scheduler.py start
Restart=always

[Install]
WantedBy=multi-user.target
```

Start service:
```bash
sudo systemctl enable job-hunter-scheduler
sudo systemctl start job-hunter-scheduler
sudo systemctl status job-hunter-scheduler
```

**Using Docker:**
```dockerfile
FROM python:3.10

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN playwright install chromium

COPY . .

CMD ["python", "notifications/scheduler.py", "start"]
```

## Best Practices

### 1. Resume Quality
- Use clear, structured resume format
- Include specific skills and technologies
- Mention years of experience
- List preferred job roles

### 2. Search Configuration
- Start with min_score=0.7 (adjust based on results)
- Use 3-5 max_jobs_per_search (avoid notification fatigue)
- Schedule daily searches (more frequent = more duplicates)
- Filter by location if you have preference

### 3. Notification Management
- Review and apply promptly
- Update resume when skills change
- Pause scheduler if not actively searching
- Use different resumes for different roles

### 4. Privacy & Security
- Never share Twilio credentials
- Use environment variables (`.env`)
- Don't commit `.env` to version control
- Rotate credentials periodically

## Cost Estimation

### Twilio Costs (approximate)
- WhatsApp messages: $0.005 per message (outbound)
- 100 notifications/month = $0.50
- 1000 notifications/month = $5.00

### OpenAI Costs (approximate)
- Resume parsing: ~$0.001 per resume
- Job ranking: ~$0.005 per 10 jobs
- 100 searches with 10 jobs each = ~$5.00/month

**Total estimated cost: $5-10/month for active job search**

## Support

**Issues:** [GitHub Issues](https://github.com/yourusername/ai_job_hunter_agent/issues)

**Questions:** Contact support or check logs:
```bash
tail -f logs/job_hunter.log
```

## Roadmap

- [ ] Telegram notifications
- [ ] Email notifications
- [ ] SMS notifications (Twilio)
- [ ] Custom notification templates
- [ ] Job application tracking
- [ ] Interview scheduling integration
- [ ] Salary insights per notification
- [ ] Company review integration
