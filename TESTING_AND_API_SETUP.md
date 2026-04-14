# Job Agent - Testing & API Configuration Guide

## Quick Start
```bash
# 1. Copy and configure environment
cp .env.example .env

# 2. Install dependencies
python3 -m pip install -r job_agent/requirements.txt
playwright install chromium

# 3. Run tests (lightweight - no heavy models)
python3 -m unittest discover -s tests -v

# 4. Run API server
uvicorn job_agent.main:app --reload

# 5. Open UI
# Open browser to http://127.0.0.1:8000/
```

---

## Part 1: API Keys & Environment Configuration

### 1.1 Required vs Optional Keys

#### **REQUIRED** (for basic operation):
| Key | Purpose | Default | Example |
|-----|---------|---------|---------|
| `JOB_AGENT_MONGO_URI` | MongoDB connection | `mongodb://localhost:27017` | Your local or cloud MongoDB |
| `JOB_AGENT_DEFAULT_PROFILE_ID` | User profile identifier | `default` | `john-doe` or `user-123` |

#### **OPTIONAL** (for enhanced features):
| Key | Purpose | Default | Note |
|-----|---------|---------|------|
| `JOB_AGENT_GROQ_API_KEY` | LLM reasoning & field resolution | (empty) | Get free at [console.groq.com](https://console.groq.com) |
| `JOB_AGENT_ENABLE_TRANSFORMER_EMBEDDINGS` | Sentence-Transformers for embeddings | `false` | Set to `true` for semantic search (heavier) |
| `JOB_AGENT_ENABLE_LLM_FALLBACK` | Ollama local LLM fallback | `false` | Set to `true` if Ollama running locally |
| `JOB_AGENT_BROWSER_HEADLESS` | Hide browser window | `false` | Set to `true` to run invisible |
| `JOB_AGENT_AUTO_SUBMIT` | Auto-submit forms at end | `false` | Set to `true` for fully automated applications |

---

### 1.2 Setup Steps

#### **Step 1: Copy Template**
```bash
cd /Users/goranshgattani/Desktop/Playground
cp .env.example .env
```

#### **Step 2: Edit `.env` File**

**Minimal Setup (dev/testing):**
```env
JOB_AGENT_MONGO_URI=mongodb://localhost:27017
JOB_AGENT_DATABASE_NAME=job_agent
JOB_AGENT_DEFAULT_PROFILE_ID=default

# Browser settings
JOB_AGENT_BROWSER_HEADLESS=false
JOB_AGENT_AUTO_SUBMIT=false

# Embeddings (use hash-based by default)
JOB_AGENT_ENABLE_TRANSFORMER_EMBEDDINGS=false
JOB_AGENT_EMBEDDING_DIMENSIONS=128
```

**Production Setup (with Groq AI):**
```env
# Get free API key from https://console.groq.com
JOB_AGENT_GROQ_API_KEY=gsk_your_api_key_here

# LLM models (these are free tier options)
JOB_AGENT_GROQ_CHUNK_MODEL=llama-3.1-8b-instant
JOB_AGENT_GROQ_REASONING_MODEL=llama-3.3-70b-versatile

# Enable semantic search with embeddings
JOB_AGENT_ENABLE_SEMANTIC_SEARCH=true
```

**Advanced Setup (with Local LLM):**
```env
# Requires Ollama running on http://127.0.0.1:11434
JOB_AGENT_ENABLE_LLM_FALLBACK=true
JOB_AGENT_OLLAMA_URL=http://127.0.0.1:11434/api/generate
JOB_AGENT_OLLAMA_MODEL=llama3.2:1b
JOB_AGENT_OLLAMA_TIMEOUT_SECONDS=10
```

---

### 1.3 Getting Groq API Key (Free)

1. Visit [console.groq.com](https://console.groq.com)
2. Sign up with email or GitHub
3. Navigate to **API Keys** → **Create New API Key**
4. Copy the key (looks like: `gsk_...`)
5. Paste into `.env`:
   ```env
   JOB_AGENT_GROQ_API_KEY=gsk_your_api_key_here
   ```
6. Models available (all free):
   - `llama-3.1-8b-instant` - Fast, good for chunking
   - `llama-3.3-70b-versatile` - Slower, better reasoning
   - `mixtral-8x7b-32768` - Good balance

---

### 1.4 Database Configuration

#### **Option A: Local MongoDB (Recommended for Dev)**
```bash
# Install MongoDB locally
# macOS:
brew tap mongodb/brew
brew install mongodb-community

# Start MongoDB:
brew services start mongodb-community

# Verify connection:
mongosh
# You should see: test>
```

#### **Option B: In-Memory Fallback (No Setup Required)**
- If MongoDB unavailable → system automatically uses in-memory storage
- **Perfect for testing** - no DB setup needed
- Data lost on restart (intentional for dev)

#### **Option C: MongoDB Atlas Cloud (Free Tier)**
```env
JOB_AGENT_MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
```
1. Create account at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Create free cluster
3. Get connection string
4. Replace username/password

---

## Part 2: Running Tests

### 2.1 All Unit Tests (No Browser, No DB Required)
```bash
source /Users/goranshgattani/Desktop/Playground/.venv/bin/activate

# Run all tests with verbose output
python3 -m unittest discover -s tests -v

# Run specific test file
python3 -m unittest tests.test_field_classifier -v

# Run single test method
python3 -m unittest tests.test_field_classifier.FieldClassifierTests.test_notice_period_is_classified_separately -v
```

**What's Tested (No Setup Required):**
- ✅ Field classification logic
- ✅ Platform detection
- ✅ Resume text extraction & chunking
- ✅ Resume knowledge retrieval
- ✅ Value resolver
- ✅ Semantic search
- ✅ Extension service
- ✅ Browser element mocking
- ✅ Form parsing logic
- ✅ Application state persistence

---

### 2.2 Individual Test Files

| Test File | What It Tests | Dependencies |
|-----------|---------------|--------------|
| `test_field_classifier.py` | Field type detection | None |
| `test_platform_detector.py` | ATS platform detection | None |
| `test_form_parser.py` | Form field extraction logic | None (uses mocks) |
| `test_browser.py` | Browser automation logic | None (uses mocks) |
| `test_resume_service.py` | Resume upload & chunking | None |
| `test_resume_knowledge_service.py` | Resume RAG & embeddings | None |
| `test_value_resolver.py` | Field value resolution | None |
| `test_extension_service.py` | Extension fill plan generation | None |
| `test_application_graph.py` | LangGraph workflow | None |
| `test_base_handler.py` | Form filling handler | None (uses mocks) |
| `test_job_agent.py` | Main agent orchestration | None (uses mocks) |
| `test_playwright_tools.py` | Browser tool wrappers | None |

---

### 2.3 Example Test Runs

```bash
# Quick smoke test (30 seconds)
python3 -m unittest tests.test_field_classifier tests.test_platform_detector -v

# Comprehensive unit tests (2 minutes)
python3 -m unittest discover -s tests -v

# With coverage report (requires coverage)
pip install coverage
coverage run -m unittest discover -s tests
coverage report
coverage html  # creates htmlcov/index.html
```

---

## Part 3: Running the Application

### 3.1 Development Server

```bash
source /Users/goranshgattani/Desktop/Playground/.venv/bin/activate

# Start with auto-reload
uvicorn job_agent.main:app --reload --host 127.0.0.1 --port 8000

# Output:
# INFO:     Uvicorn running on http://127.0.0.1:8000
# INFO:     Application startup complete
```

### 3.2 Web UI

**Open in Browser:**
```
http://127.0.0.1:8000/
```

**Features:**
1. **Upload Resume** (saved to MongoDB)
2. **Create Profile** (name, email, skills, etc.)
3. **Start Application** (paste job URL, click Start)
4. **Real-time Progress** (via WebSocket)
5. **Answer Questions** (when agent needs clarification)
6. **View Results** (fields filled, questions asked, etc.)

---

### 3.3 Testing via WebSocket (CLI)

```bash
# Install websocat
brew install websocat

# Connect to WebSocket
websocat ws://127.0.0.1:8000/ws/stream

# Send application start (paste this, press Enter):
{"type":"start","url":"https://company.workdayjobs.com/en-US/job/123","profile_id":"default"}

# You'll receive real-time updates:
{"type":"status","message":"Detected platform: workday"}
{"type":"status","message":"Opening workday job page"}
{"type":"status","message":"Processing form step 1 (5 fields)"}
{"type":"question","field":"First Name","question":{...}}
```

---

### 3.4 Chrome Extension Testing

1. **Enable Extension:**
   - Open `chrome://extensions/`
   - Toggle **Developer mode**
   - **Load unpacked** → Select `/Users/goranshgattani/Desktop/Playground/chrome_extension`

2. **Use on Job Site:**
   - Navigate to job application
   - Click **Job Agent** icon
   - Click **Fill Form**
   - Extension calls `/api/extension/resolve`
   - Returns auto-fill recommendations

3. **Extension Flow:**
   ```
   1. Content script extracts form fields
   2. POST to /api/extension/resolve
   3. Get fill plan (fills, blocked, skipped)
   4. Auto-fill allowed fields
   5. Show blocked/skipped alerts
   ```

---

## Part 4: Integration Testing (With Real Browser)

### 4.1 Manual Testing Setup

```bash
# Terminal 1: Start API server
source .venv/bin/activate
uvicorn job_agent.main:app --reload

# Terminal 2: Open UI
open http://127.0.0.1:8000/

# Terminal 3: Monitor logs (optional)
tail -f /tmp/job_agent.log
```

### 4.2 Test Scenarios

#### **Scenario 1: Field Classification**
- Upload resume
- Visit job site
- Verify field types detected correctly
- Check that company_name → "company name" field

#### **Scenario 2: Resume Extraction**
- Upload multi-page resume
- Check MongoDB chunks created
- Verify embeddings generated
- Test semantic search

#### **Scenario 3: Automated Filling**
- Upload resume with known values
- Apply to test job posting
- Verify auto-filled fields
- Check for human escalation on ambiguous fields

#### **Scenario 4: Platform-Specific**
- Test Workday × Greenhouse × Lever separately
- Verify platform detection working
- Check handler routing

#### **Scenario 5: Continuation**
- Start application
- Pause partway through
- Close browser
- Resume later
- Verify state persisted

---

## Part 5: Debugging & Troubleshooting

### 5.1 Common Issues

#### **Issue: MongoDB Connection Failed**
```
# Error: Server selection timed out
# Solution:
mongo_check=$(mongosh --eval "db.adminCommand('ping')")
if [ $? -ne 0 ]; then
  echo "MongoDB not running. Starting..."
  brew services start mongodb-community
fi
```

#### **Issue: Playwright Not Installed**
```bash
playwright install chromium
# or
python3 -m playwright install
```

#### **Issue: Groq API Key Invalid**
```bash
# Test your key:
curl -X POST https://api.groq.com/openai/v1/chat/completions \
  -H "Authorization: Bearer gsk_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-3.1-8b-instant","messages":[{"role":"user","content":"test"}]}'
```

#### **Issue: Browser Permission Denied**
```bash
# macOS:
spctl --add --label "My Site" /path/to/browser

# Or allow in System Preferences > Security & Privacy
```

---

### 5.2 Enable Debug Logging

```python
# In main.py or any module:
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("job_agent")
logger.debug("Detailed message here")
```

```bash
# Run with debug output:
export JOB_AGENT_DEBUG=1
uvicorn job_agent.main:app --log-level debug
```

---

### 5.3 Inspect MongoDB Data

```bash
# Connect to MongoDB
mongosh

# Use job_agent database
use job_agent

# View collections
show collections

# Query profiles
db.profile.find()

# Query resume chunks
db.resume_chunks.find({"profile_id": "default"}).limit(1)

# Query applications
db.applications.find().sort({created_at: -1}).limit(5)

# Query learned answers
db.answers.find()
```

---

## Part 6: Performance & Configuration Tuning

### 6.1 For Fast Testing (No Wait)
```env
JOB_AGENT_BROWSER_TIMEOUT_MS=5000
JOB_AGENT_BROWSER_FORM_WAIT_TIMEOUT_MS=2000
JOB_AGENT_BROWSER_SLOW_MO_MS=0
```

### 6.2 For Debugging (With Waits)
```env
JOB_AGENT_BROWSER_TIMEOUT_MS=60000
JOB_AGENT_BROWSER_FORM_WAIT_TIMEOUT_MS=10000
JOB_AGENT_BROWSER_SLOW_MO_MS=500
JOB_AGENT_BROWSER_HEADLESS=false
```

### 6.3 For Production (Load Optimization)
```env
JOB_AGENT_BROWSER_HEADLESS=true
JOB_AGENT_ENABLE_TRANSFORMER_EMBEDDINGS=true
JOB_AGENT_SIMILARITY_THRESHOLD=0.85
JOB_AGENT_AUTO_SUBMIT=true
JOB_AGENT_ENABLE_SEMANTIC_SEARCH=true
```

---

## Part 7: API Reference for Testing

### 7.1 Upload Resume
```bash
curl -X POST http://127.0.0.1:8000/api/profile/resume \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/resume.pdf" \
  -F "profile_id=default"

# Response:
# {
#   "message": "Resume stored successfully",
#   "filename": "resume.pdf",
#   "file_id": "507f1f77bcf86cd799439011"
# }
```

### 7.2 Get Resume Metadata
```bash
curl http://127.0.0.1:8000/api/profile/resume?profile_id=default

# Response:
# {
#   "filename": "resume.pdf",
#   "file_id": "507f1f77bcf86cd799439011",
#   "chunk_count": 12
# }
```

### 7.3 Extension Resolution
```bash
curl -X POST http://127.0.0.1:8000/api/extension/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://company.workdayjobs.com/en-US/job",
    "profile_id": "default",
    "fields": [
      {
        "field_id": "first-name",
        "label": "First Name",
        "tag_name": "input",
        "required": true
      }
    ]
  }'

# Response:
# {
#   "fills": [
#     {"field_id": "first-name", "value": "John", "confidence": 0.95}
#   ],
#   "blocked": [],
#   "skipped": [],
#   "stats": {...}
# }
```

---

## Part 8: Checklist Before Production

- [ ] MongoDB running or cloud connection configured
- [ ] `.env` file created with `JOB_AGENT_GROQ_API_KEY` (optional but recommended)
- [ ] `playwright install chromium` executed
- [ ] All tests passing: `python3 -m unittest discover -s tests -v`
- [ ] UI loads at `http://127.0.0.1:8000/`
- [ ] Resume uploads successfully
- [ ] Sample job application completes without errors
- [ ] WebSocket connection stable during 5+ minute run
- [ ] Chrome extension loads and fills fields
- [ ] State persists after browser restart

---

## Summary: 3-Minute Setup

```bash
# 1. Configure (60 seconds)
cp .env.example .env
# Edit .env: set GROQ_API_KEY (optional), MONGO_URI (optional)

# 2. Test (60 seconds)
python3 -m unittest discover -s tests -v

# 3. Run (60 seconds)
uvicorn job_agent.main:app --reload
# Visit http://127.0.0.1:8000/
```

**That's it!** The system works with sensible defaults and falls back gracefully.
