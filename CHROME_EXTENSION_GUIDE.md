# Job Agent Chrome Extension - Complete Setup & Usage Guide

## Overview

The Job Agent Chrome Extension allows you to **fill job applications directly in your browser tab** without opening a separate window. It's faster, cleaner, and keeps you in your workflow.

**Key Benefits:**
- ✅ Stay in your current browser tab
- ✅ Real-time form filling suggestions
- ✅ Pause on complex questions, resume when ready
- ✅ See suggestions before committing
- ✅ Activity log for transparency
- ✅ Works with 11+ ATS platforms (Workday, Greenhouse, Lever, etc.)

---

## Part 1: Installation & Setup

### Step 1: Verify Backend Is Running

The extension **requires** the Job Agent backend API running locally:

```bash
cd /Users/goranshgattani/Desktop/Playground

# Terminal 1: Start backend
source .venv/bin/activate
uvicorn job_agent.main:app --reload --host 127.0.0.1 --port 8000

# You should see:
# INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Step 2: Upload Your Resume

**Via Web UI:**
1. Open http://127.0.0.1:8000/ in browser
2. Click **Upload Resume**
3. Select your resume (PDF, DOCX, TXT, RTF)
4. Wait for upload confirmation

**Resume is now indexed with:**
- ✓ Work history (companies, titles, dates)
- ✓ Skills and technologies
- ✓ Location and contact info
- ✓ Experience summary

### Step 3: Load the Chrome Extension

#### Option A: Development Mode (Recommended)
```
1. Open Chrome → chrome://extensions/
2. Toggle "Developer mode" (top-right)
3. Click "Load unpacked"
4. Navigate to: /Users/goranshgattani/Desktop/Playground/chrome_extension
5. Confirm
```

You should see **"Job Agent Form Filler v0.1.0"** in your extensions list.

#### Option B: Using Extension ID
If the extension doesn't appear after loading:
```
1. Verify the files in chrome_extension/:
   ✓ manifest.json
   ✓ popup.html
   ✓ popup.js
   ✓ content-script.js
   ✓ background.js

2. Check for errors: chrome://extensions/?errors
3. Reload the extension (circular arrow icon)
```

---

## Part 2: Using the Extension on Job Sites

### Step 1: Navigate to Job Application

1. Go to any job site (Workday, Greenhouse, LinkedIn, etc.)
2. Click **"Apply"** or similar button to start application
3. Wait for form to load completely

### Step 2: Open Extension Popup

Click the **Job Agent icon** (puzzle piece) in Chrome toolbar:

```
┌─────────────────────────────────────┐
│  Job Agent Form Filler  [Refresh]   │
├─────────────────────────────────────┤
│                                     │
│  Status: [Idle]                    │
│                                     │
│  Backend URL                        │
│  [http://127.0.0.1:8000]           │
│                                     │
│  Profile ID                         │
│  [default]                          │
│                                     │
│  [Start] [Resume] [Pause]          │
│                                     │
│  Activity Log                       │
│  No activity yet.                   │
│                                     │
└─────────────────────────────────────┘
```

### Step 3: Configure Settings (if needed)

- **Backend URL**: Should be `http://127.0.0.1:8000`
  - Change if running on different port/machine
  
- **Profile ID**: Should be `default`
  - Change to use different profile with different resume/preferences

### Step 4: Click START

```
[Start] button
    ↓
Extension scans page for form fields
    ↓
Sends form structure to backend
    ↓
Backend calls /api/extension/resolve
    ↓
Gets fill recommendations
    ↓
Auto-fills fields with high confidence
```

**You'll see in Activity Log:**
```
[14:23:45] info
Scanned fields
fields: [
  {label: "First Name", required: true},
  {label: "Email", required: true},
  {label: "Resume/CV", required: true}
]

[14:23:46] info
Resolved fill plan
fills: 3, blocked: 1, skipped: 2

[14:23:47] info
Filling form on current page
```

### Step 5: Review Filled Form

The extension will:

✅ **Auto-fill fields with:**
- Name, email, phone
- Work history (companies, titles, dates)
- Skills
- Location
- Experience years

⏸️ **Pause on blocked fields:**
- Resume/CV upload (requires manual selection)
- Cover letter (if not available)
- Unknown custom fields

❓ **Skip optional fields** that agent can't resolve

### Step 6: Handle Blockers

When the extension **stops** (status = "Paused"):

```
Status: [Paused]

Paused because:
"Resume/CV: manual_upload_required"
```

**Your actions:**
1. **Manually upload resume** if field exists
2. Click **[Resume]** to continue
3. Repeat for other blockers

### Step 7: Multi-Step Forms

For forms with **Next/Continue buttons:**

Extension automatically:
```
Step 1: Fill fields → Click Next
    ↓
Step 2: Scan new fields → Fill again
    ↓
Step 3: Click Submit (if auto_submit enabled)
    ↓
Done
```

---

## Part 3: Activity Log & Debugging

### What the Log Shows

```
[14:23:47] info
Filling form on current page
fills: [
  {field_id: "first-name", value: "John", confidence: 0.95},
  {field_id: "email", value: "john@example.com", confidence: 1.0}
]

[14:23:48] info
Detected blocked field
{label: "Resume/CV", reason: "manual_upload_required"}

[14:23:49] info
Form step completed
fields_detected: 5, fields_filled: 3
```

### Common Messages

| Message | Meaning | Action |
|---------|---------|--------|
| `Scanned fields` | Found form fields | Check if all fields detected |
| `Resolved fill plan` | Backend processed fields | See how many can auto-fill |
| `Filling form on current page` | Extension injecting values | Wait for completion |
| `Detected blocked field` | Can't auto-fill (manual needed) | Upload resume or enter data |
| `Form step completed` | Ready to click Next | Click Next or [Resume] |
| `Form filler paused` | Waiting for your action | Upload file or click [Resume] |

### Refresh Activity Log

Click **[Refresh]** button to reload current state and recent logs.

---

## Part 4: Configuration Options

### Backend URL

**Default:** `http://127.0.0.1:8000`

**Change if:**
- Running backend on different port:
  ```
  http://127.0.0.1:8001
  ```
- Running backend on different machine:
  ```
  http://192.168.1.100:8000
  ```
- Using cloud deployment:
  ```
  https://job-agent.example.com
  ```

### Profile ID

**Default:** `default`

**Change to:**
- Use different resume:
  ```
  profile_id=senior-engineer
  ```
- Support multiple candidates:
  ```
  profile_id=candidate-1
  profile_id=candidate-2
  ```

Each profile has its own:
- Resume chunks
- Learned answers
- Field preferences
- Application history

---

## Part 5: Advanced Usage

### Resume With Hidden Fields

Some job sites hide resume fields (auto-detected):

```
Extension detects "hidden" file input
    ↓
Won't show in form, but extension finds it
    ↓
Auto-uploads resume without user seeing
    ↓
Form updates with new fields
```

### JavaScript Form Fields

Modern job sites use React/Vue/Angular forms:

```
Extension hooks into form events
    ↓
Waits for fields to render (document_idle)
    ↓
Scans for dynamically created elements
    ↓
Injects values and triggers change events
    ↓
Form framework recognizes updates
```

### Multi-Page Applications

For 5+ step applications:

```
Step 1 → Fill → Next → Step 2 → Fill → Next
    ↓
Step 3 → Fill → Next → Step 4 → Fill → Next
    ↓
Step 5 → Fill → Submit → Done
```

Each step is scanned, fields identified, and values injected.

---

## Part 6: Troubleshooting

### Extension Not Appearing

**Problem:** No Job Agent icon in toolbar

**Solutions:**
```
1. Check extension loaded:
   chrome://extensions/ → Search "Job Agent"
   
2. If showing but hidden:
   Click extensions icon (puzzle) → Pin "Job Agent"
   
3. If errors shown:
   chrome://extensions/?errors → Check details
```

### Backend Connection Failed

**Error:** "Unable to connect to http://127.0.0.1:8000"

**Solutions:**
1. Verify backend is running:
   ```bash
   curl http://127.0.0.1:8000/
   # Should return HTML
   ```

2. Check correct port in extension settings

3. Restart backend:
   ```bash
   # Kill existing process
   pkill -f "uvicorn job_agent"
   
   # Start new
   uvicorn job_agent.main:app --reload
   ```

### Form Not Scanning

**Problem:** "No fields detected" after clicking Start

**Solutions:**
1. Wait for form to fully load (5-10 seconds)
2. Click [Start] again
3. Manually scroll down to reveal hidden fields
4. Try [Pause] then [Resume] to re-scan

**For JavaScript forms:**
- Extension might need time for React to render
- Click [Refresh] to re-scan

### Resume Not Uploading

**Problem:** Resume field shows "blocked"

**Solutions:**
1. Ensure resume uploaded to Job Agent:
   - Go to http://127.0.0.1:8000/
   - Click "Upload Resume" (if not done)
   
2. Try manual upload:
   - Click file upload field
   - Select same resume manually
   - Click [Resume]

### Fields Not Filling

**Problem:** Values don't appear in form

**Solutions:**
1. Check logs for `confidence` score:
   - High confidence (0.9+) → Should auto-fill
   - Low confidence (< 0.6) → Blocked for safety
   
2. Manually enter values for low-confidence fields

3. Teach the extension by answering question:
   - Extension will remember next time
   - Learned answers stored in DB

---

## Part 7: Tips & Best Practices

### Resume Quality Matters

**Upload good resume for:**
- ✓ Consistent formatting
- ✓ Clear company names
- ✓ Visible dates
- ✓ Skills section
- ✓ Contact info at top

**Extension uses it to:**
- Extract work history
- Find relevant skills
- Locate dates and locations
- Identify contact information

### Set Up Multiple Profiles

```bash
# Senior Engineer
Backend URL: http://127.0.0.1:8000
Profile ID: senior-engineer

# Junior Developer  
Backend URL: http://127.0.0.1:8000
Profile ID: junior-developer

# Each has separate resume & preferences
```

Switch by changing Profile ID in popup.

### Answer Questions to Teach Agent

When extension asks for clarification:
1. Answer honestly
2. Answer is saved
3. Similar questions answered automatically next time

Example:
- "Notice Period?" → Answer "2 weeks" → Saved
- Next application asks → Auto-filled with "2 weeks"

### Pause Strategically

Use **[Pause]** when:
- Application asks specific questions
- You want to modify auto-filled values
- Resume upload field appears
- Site-specific customizations needed

Then **[Resume]** after you're ready.

---

## Part 8: Keyboard Shortcuts

Currently: No keyboard shortcuts implemented

**Soon:**
- `Alt+J` - Open Job Agent popup
- `Alt+S` - Start form filler
- `Alt+R` - Resume form filler

---

## Part 9: Privacy & Safety

### What Stays Local

✓ All form values
✓ Resume content
✓ Learned answers
✓ Application history

**Stored in:** `chrome.storage.local` (encrypted by Chrome)

### What Goes to Server

Only when you click [Start]:
- Form field list (no values)
- Profile ID
- API call to `/api/extension/resolve`

**Nothing sent to:** Cloud, third parties, or external services

---

## Part 10: Getting Help

### Check Extension Logs

```javascript
// In browser console (F12):
chrome.storage.local.get((items) => {
  console.log("Backend URL:", items.jobAgentBackendUrl);
  console.log("Profile ID:", items.jobAgentProfileId);
});
```

### Verify Backend API

```bash
# Test API endpoint
curl -X POST http://127.0.0.1:8000/api/extension/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/jobs",
    "profile_id": "default",
    "fields": [
      {"field_id": "first-name", "label": "First Name", "required": true}
    ]
  }'

# Should get back fill recommendations
```

### Check Resume Indexed

```bash
# Via Web UI:
1. Open http://127.0.0.1:8000/
2. Click "Get Resume Metadata"
3. Should show chunk count

# Via API:
curl http://127.0.0.1:8000/api/profile/resume?profile_id=default
```

---

## Summary - Quick Start

```
1️⃣  Start backend: uvicorn job_agent.main:app --reload
2️⃣  Upload resume: http://127.0.0.1:8000/ → Upload Resume
3️⃣  Load extension: chrome://extensions/ → Load unpacked
4️⃣  Navigate to job: Go to Workday/Greenhouse/etc
5️⃣  Click extension: Job Agent icon → [Start]
6️⃣  Review & submit: Handle blockers → Fill form → Submit
```

**That's it!** The extension handles the rest.
