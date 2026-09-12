# 🍽️ CRG Meridian Restaurant — 100% Free 24/7 AI Review Reply System

A fully automated, $0/month AI review reply bot and monitoring dashboard for CRG Meridian Restaurant (Madikeri, Karnataka, India).

---

## 💰 100% Free Stack — Cost Breakdown

| Component | Service | Cost |
| :--- | :--- | :--- |
| 🖥️ **Server (24/7)** | Oracle Cloud Always Free (Ampere ARM VM) | $0 forever |
| 🤖 **AI Replies** | Groq Free Tier (`openai/gpt-oss-120b`) | $0 |
| 📡 **Google Reviews API** | Google Business Profile API | $0 |
| 🗄️ **Database** | SQLite (`reviews.db`) | $0 |
| 📲 **Notifications** | Telegram Bot API | $0 |
| 🌐 **Dashboard** | Flask Web UI | $0 |
| **Total** | | **$0/month forever** |

---

## 🔄 How It Works

```text
Every 30 min:
  → Fetch all reviews from Google Business Profile
  → Skip reviews already replied to
  → Store new reviews in SQLite

Every 30 min (5 min offset):
  → Check each pending review
  → Is it 24+ hours old?
      NO  → Skip this cycle, wait
      YES → Send review to Groq (GPT-OSS 120B) → Generate owner reply draft
  → Routing based on star rating:
      ⭐⭐⭐⭐⭐ (4–5 Stars):
        → Auto-post reply via GBP API
        → Send Telegram confirmation
        → Mark status as 'posted'
      ⭐–⭐⭐⭐ (1–3 Stars):
        → Save AI draft to DB
        → Send Telegram alert with draft + dashboard link
        → Owner reviews/edits & clicks "Approve"

Every 10 min:
  → Check for approved drafts in database
  → Post them via GBP API
  → Mark status as 'posted'
```

---

## 📁 Project Structure

```text
crg_review_bot/
├── app.py               # Flask web dashboard & manual trigger API
├── gbp_client.py        # Google Business Profile API OAuth & reply client
├── ai_client.py         # Groq API integration (GPT-OSS 120B)
├── worker.py            # APScheduler 30-min & 10-min background jobs
├── db.py                # SQLite database interface
├── notifier.py          # Telegram Bot notifications & alerts
├── requirements.txt     # Python dependencies
├── .env                 # Environment secrets & credentials
├── token.json           # Auto-generated OAuth token (after first login)
└── templates/
    ├── login.html       # Password-protected login page
    ├── dashboard.html   # Main dashboard with stats & review list
    └── review_detail.html # Review inspection, AI regeneration, & approval
```

---

## 🚀 Step-by-Step Setup Guide

### Step 1 — Sign up for Oracle Cloud Free Tier
1. Go to [cloud.oracle.com](https://cloud.oracle.com) → **Sign Up**.
2. Enter your details and choose a Home Region (e.g., **US East - Ashburn** for best availability).
3. Add a credit card for identity verification only (no charges apply for Always Free usage).
4. Create a VM: **Compute** → **Instances** → **Create Instance**.
   - **Shape**: `VM.Standard.A1.Flex` (ARM Ampere) → select **2 OCPUs + 12GB RAM** (or up to 4 OCPU / 24GB RAM).
   - **OS**: Ubuntu 22.04 LTS.
5. Download your private SSH key (`.key`/`.pem`).
6. Connect via SSH:
   ```bash
   ssh -i /path/to/private_key ubuntu@YOUR_SERVER_IP
   ```
   *(If you encounter "Out of Capacity", retry after a few hours or try AD-2 / AD-3 availability domains).*

---

### Step 2 — Server Environment Setup
On your server terminal, execute:
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3, pip, and Git
sudo apt install python3 python3-pip git -y

# Clone or transfer your project files
git clone https://github.com/YOUR_USERNAME/crg-review-bot.git
cd crg-review-bot

# Install required Python packages
pip3 install -r requirements.txt

# Configure your environment variables
nano .env
```
*(Paste your `.env` values and press `Ctrl+O`, `Enter`, and `Ctrl+X` to save).*

---

### Step 3 — Get Groq API Key (Free, Instant)
1. Go to [console.groq.com](https://console.groq.com) and create a free account.
2. Navigate to **API Keys** → **Create Key**.
3. Add it to your `.env`:
   ```env
   GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
   GROQ_MODEL=openai/gpt-oss-120b
   ```

---

### Step 4 — Set up Telegram Bot
1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, choose a name and username, and copy the **HTTP API Token**.
3. Open a chat with your newly created bot and press **Start**.
4. Search for [@userinfobot](https://t.me/userinfobot), send `/start`, and copy your numeric **Id**.
5. Add both to `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
   TELEGRAM_CHAT_ID=your_personal_chat_id
   ```

---

### Step 5 — One-Time Google OAuth Authentication
1. Download `credentials.json` from the Google Cloud Console (OAuth 2.0 Client IDs for Desktop).
2. Place `credentials.json` in the `crg_review_bot/` directory.
3. Run the one-time authentication script:
   ```bash
   python3 -c "import gbp_client; gbp_client.get_credentials()"
   ```
4. Follow the prompt to authorize access with the Google account managing CRG Meridian. `token.json` will be created and auto-refreshed going forward.

---

### Step 6 — Run 24/7 with PM2
```bash
# Install Node.js & PM2
sudo apt install nodejs npm -y
sudo npm install -g pm2

# Start the review bot application
pm2 start "python3 app.py" --name crg-review-bot

# Configure PM2 to start automatically on system reboot
pm2 save
pm2 startup
# (Run the generated sudo env command printed in terminal)

# View live application logs anytime
pm2 logs crg-review-bot
```

---

### Step 7 — Access the Web Dashboard
- Open in your browser: `http://YOUR_SERVER_IP:5000`
- To open port 5000:
  - In Oracle Cloud Console: **Networking** → **Virtual Cloud Networks** → Click your VCN → **Security Lists** → **Default Security List**.
  - Click **Add Ingress Rules**:
    - **Source CIDR**: `0.0.0.0/0`
    - **IP Protocol**: TCP
    - **Destination Port Range**: `5000`
  - In Ubuntu terminal:
    ```bash
    sudo ufw allow 5000/tcp
    ```
