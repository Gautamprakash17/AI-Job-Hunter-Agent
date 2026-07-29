# 🤖 Custom Job Search Agent with WhatsApp Notifications

> Upload your resume once, and let AI automatically search for jobs and notify you on WhatsApp!

## 🎯 What is This?

An **autonomous AI agent** that:
- 🔍 Searches LinkedIn, Indeed, and Naukri for jobs matching your resume
- 🤖 Uses AI to rank jobs by relevance (not just keyword matching)
- 📱 Sends WhatsApp notifications for high-match opportunities
- ⏰ Can run on a schedule (hourly, daily, weekly)
- 🎯 Never sends duplicate notifications
- 📊 Tracks all searches and results

## ⚡ Quick Start

### 1. Setup (One-Time)

```bash
# Install dependencies
pip install -r requirements.txt

# Configure Twilio (for WhatsApp)
# Sign up at https://www.twilio.com
# Get your credentials and add to .env:
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_NUMBER=+14155238886
```

### 2. Upload Resume & Run

**Option A: Dashboard (Easiest)**
```bash
python main.py dashboard
# → Go to "Custom Search" tab
# → Upload resume with your WhatsApp number
# → Click "Search & Notify Now" or "Schedule Search"
```

**Option B: Command Line**
```bash
# One-time search
python agents/custom_search_agent.py 1 +919876543210 "Bangalore"

# Schedule daily searches at 9 AM
python notifications/scheduler.py add 1 +919876543210 --frequency daily --hour 9

# Start scheduler (keeps running)
python notifications/scheduler.py start
```

**Option C: Demo Script**
```bash
python examples/custom_search_demo.py \
  --phone +919876543210 \
  --resume resume.pdf \
  --target-role "AI Engineer" \
  --schedule daily
```

### 3. Receive Notifications 📱

```
🔥 Job Match #1 (87% match)

*Senior AI Engineer*
🏢 TechCorp
📍 Bangalore, India
🌐 Portal: LinkedIn

🔗 Apply: https://linkedin.com/jobs/123

---
💼 AI Job Hunter Agent
```

## 🎨 Features

### 🤖 Autonomous Job Hunting
- Upload resume once, AI handles the rest
- Searches multiple job portals simultaneously
- Smart ranking using semantic similarity (AI-powered)
- Configurable match threshold (default: 70%)

### 📱 WhatsApp Notifications
- Instant alerts on your phone
- Rich formatting with job details
- Direct apply links
- Multiple jobs in one message

### ⏰ Scheduled Searches
- **Hourly**: Every hour
- **Every 4h/12h**: Custom intervals
- **Daily**: Once per day at specific time
- **Weekly**: Once per week (e.g., every Monday)

### 📊 Search History
- Track all searches and results
- View notification history
- Analyze job discovery patterns
- Monitor success rates

### 🎯 Smart Features
- **Deduplication**: Never get notified about same job twice
- **Threshold Filtering**: Only high-match jobs (customizable)
- **Multi-Portal**: LinkedIn, Indeed, Naukri in one search
- **Location Filtering**: Search by city or "Remote"

## 📖 Usage Examples

### Example 1: Quick One-Time Search
```bash
# Search and get WhatsApp notification immediately
python agents/custom_search_agent.py 1 +919876543210
```

### Example 2: Daily Morning Updates
```bash
# Get job alerts every morning at 9 AM
python notifications/scheduler.py add 1 +919876543210 \
  --frequency daily \
  --hour 9 \
  --location "Remote"
```

### Example 3: Frequent Updates
```bash
# Get alerts every 4 hours
python notifications/scheduler.py add 1 +919876543210 \
  --frequency every_4h
```

### Example 4: Using the API
```bash
curl -X POST http://localhost:8000/api/custom-search \
  -H "Content-Type: application/json" \
  -d '{
    "resume_id": 1,
    "user_phone": "+919876543210",
    "location": "Bangalore",
    "min_score": 0.7,
    "max_jobs_per_search": 5
  }'
```

## 🔧 Configuration

### Search Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `resume_id` | Your resume ID in database | Required |
| `user_phone` | WhatsApp number (+country + number) | Required |
| `location` | City or "Remote" | Any |
| `min_score` | Minimum match score (0-1) | 0.7 |
| `max_jobs_per_search` | Max jobs to notify | 5 |
| `portals` | Job sites to search | All |

### Schedule Frequencies

| Frequency | Description | When It Runs |
|-----------|-------------|--------------|
| `hourly` | Every hour | 00:00, 01:00, 02:00... |
| `every_4h` | Every 4 hours | 00:00, 04:00, 08:00... |
| `every_12h` | Every 12 hours | 00:00, 12:00 |
| `daily` | Once per day | Your chosen time |
| `weekly` | Once per week | Monday at your chosen time |

## 📱 Phone Number Format

**Correct formats:**
- ✅ `+919876543210` (India)
- ✅ `+12025551234` (USA)
- ✅ `+447700123456` (UK)

**Incorrect formats:**
- ❌ `9876543210` (missing country code)
- ❌ `+91 98765 43210` (spaces)
- ❌ `+91-9876543210` (hyphens)

## 🎯 How It Works

```
1. Upload Resume
   └─> AI parses and extracts your profile

2. Search Jobs
   ├─> LinkedIn scraping
   ├─> Indeed scraping
   └─> Naukri scraping

3. Rank by Relevance
   └─> AI semantic similarity (not just keywords)

4. Filter & Deduplicate
   ├─> Remove low matches (< 70%)
   └─> Remove already-notified jobs

5. WhatsApp Notification
   └─> Instant alert with top matches

6. Track History
   └─> Save results to database
```

## 📊 Dashboard Features

### Upload & Configure
- Upload resume (PDF/TXT)
- Set WhatsApp number
- Configure preferences (location, min score)

### One-Time Search
- Search immediately
- Get instant WhatsApp notification
- View results in UI

### Scheduled Search
- Set frequency (hourly/daily/weekly)
- Choose time of day
- Start/stop scheduler

### Search History
- View all past searches
- See jobs found vs notified
- Track notification success

## 🔒 Privacy & Security

- ✅ Phone numbers stored securely
- ✅ Twilio credentials in .env (not committed)
- ✅ Local database (SQLite)
- ✅ No data sharing
- ✅ Optional feature (works without WhatsApp)

## 💰 Cost

### Twilio WhatsApp (approximate)
- $0.005 per message
- 100 notifications = $0.50
- 1000 notifications = $5.00

### OpenAI API (approximate)
- Resume parsing: $0.001 per resume
- Job ranking: $0.005 per 10 jobs
- 100 searches = ~$5.00

**Total: $5-10/month for active job search**

## 🐛 Troubleshooting

### No WhatsApp messages?
1. Check Twilio credentials in `.env`
2. Activate WhatsApp sandbox (send "join" message)
3. Verify phone number format (+country + number)
4. Check logs for errors

### Scheduler not running?
```bash
# Start manually
python notifications/scheduler.py start

# Check status
python notifications/scheduler.py list
```

### No jobs found?
1. Try lowering min_score (0.6 instead of 0.7)
2. Remove location filter
3. Check if scrapers are working
4. Try different job portals

## 📚 Documentation

- **[Complete Guide](CUSTOM_SEARCH_GUIDE.md)** - Setup, usage, troubleshooting
- **[Flow Diagrams](custom_search_flow.md)** - Architecture and data flow
- **[Feature Summary](FEATURE_SUMMARY.md)** - Implementation details
- **[Main README](../README.md)** - Project overview

## 🎯 Examples

### Example Script Output
```
$ python agents/custom_search_agent.py 1 +919876543210 "Remote"

Starting custom search for resume_id=1, phone=+919876543210
Discovering jobs for role: AI Engineer
Ranking 45 jobs
Sending WhatsApp notifications for 5 jobs

=== Custom Search Results ===
Success: True
Jobs Found: 45
Jobs Notified: 5
Notification Sent: True

Top Matches:
1. Senior AI Engineer @ TechCorp - Score: 0.87
2. ML Engineer @ StartupXYZ - Score: 0.82
3. AI/ML Lead @ BigTech - Score: 0.79
4. Machine Learning Engineer @ DataCo - Score: 0.76
5. AI Research Engineer @ AILabs - Score: 0.73

✅ Check your WhatsApp (+919876543210) for job notifications!
```

### Scheduler Output
```
$ python notifications/scheduler.py add 1 +919876543210 --frequency daily --hour 9

✅ Scheduled search added: search_1
📱 Notifications will be sent to +919876543210
🔍 Searching: All locations
⏰ Running: Daily at 09:00

$ python notifications/scheduler.py start

🚀 Starting job search scheduler...
✅ Scheduler is running. Press Ctrl+C to stop.

[2024-01-15 09:00:00] Running scheduled search for resume_id=1
[2024-01-15 09:00:32] Scheduled search completed: found=38, notified=4
```

## 🚀 Next Steps

1. **Set up Twilio** → Get WhatsApp working
2. **Upload Resume** → Via dashboard or API
3. **Test One-Time Search** → Verify notifications work
4. **Schedule Automatic Searches** → Set it and forget it
5. **Monitor History** → Track your job search progress

## 🤝 Contributing

Feature suggestions? Found a bug? Open an issue!

## 📝 License

Same as main project.

---

**Made with ❤️ to make job searching effortless!**

Questions? Check the [Complete Guide](CUSTOM_SEARCH_GUIDE.md) or open an issue.
