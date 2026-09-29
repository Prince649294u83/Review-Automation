# 🚀 24/7 Google Review Bot via Make.com (Zero Ban Risk Guide)

This guide shows you how to use **Make.com** (formerly Integromat) as an authorized, pre-verified bridge between **Google Business Profile** and your **CRG Review Bot**.

---

## 💡 Why This Setup is 100% Safe & Ban-Proof

1. **Official Google Enterprise Partner:** Make.com is already approved by Google. You connect via their official OAuth app.
2. **No Developer Review Needed:** You do **not** need to request access to the Google Business Profile API or go through developer verification.
3. **100% Free:** Make.com gives you **1,000 operations per month** for free. A restaurant receiving 20–50 reviews a month uses less than 150 operations per month.
4. **Runs 24/7 in the Cloud:** Automatically checks for new reviews around the clock, even when your personal computer is off.

---

## 🛠️ Step 1 — Create Your Free Make.com Account

1. Go to [make.com](https://www.make.com) and click **Get started free**.
2. Sign up and navigate to your dashboard.

---

## 🔄 Step 2 — Build Scenario 1: New Review Ingestion & Auto-Reply

This scenario polls Google Business Profile 24/7, sends review details to your Python bot, and immediately posts 4–5 star AI replies back to Google.

### Step 2.1 — Add the Google My Business Trigger
1. Click **Create a new scenario**.
2. Click the `+` button and search for **Google My Business**.
3. Select trigger: **Watch Reviews**.
4. Click **Create a connection**:
   - Sign in with the Google Account that manages CRG Meridian Restaurant.
   - Click **Allow** to authorize Make.com to access the business listing.
5. Select your **Account** and **Location** (CRG Meridian).
6. Set **Limit**: `10`.

### Step 2.2 — Add the HTTP Webhook to Call Your Bot
1. Add a second module: search for **HTTP** and choose **Make a request**.
2. Configure the HTTP module:
   - **URL:** `https://YOUR_BOT_DOMAIN_OR_IP/api/webhook/review-received`
   - **Method:** `POST`
   - **Headers:**
     - Name: `Content-Type`, Value: `application/json`
     - Name: `X-Webhook-Secret`, Value: *(Value of `WEBHOOK_SECRET` in your `.env`)*
   - **Body type:** `Raw`
   - **Content type:** `JSON (application/json)`
   - **Request content:**
     ```json
     {
       "review_id": "{{1.reviewId}}",
       "reviewer_name": "{{1.reviewer.displayName}}",
       "star_rating": "{{1.starRating}}",
       "comment": "{{1.comment}}",
       "review_time": "{{1.createTime}}"
     }
     ```
   - **Parse response:** `Yes`

### Step 2.3 — Add a Router for Star-Rating Routing
1. Add a **Router** module after the HTTP module.

#### Route A (Auto-Reply for 4 & 5 Stars):
- **Filter:** Set condition `2.data.action` **Equal to** `reply`
- Add module: **Google My Business** -> **Create/Update a Reply**
  - **Location:** CRG Meridian
  - **Review:** `{{1.name}}`
  - **Reply:** `{{2.data.reply_text}}`

#### Route B (1 to 3 Stars — Human-in-the-Loop):
- **Filter:** Set condition `2.data.action` **Equal to** `hold_for_approval`
- *(No further action needed in Make.com. Your Python bot has already recorded the review in SQLite and sent a Telegram notification with an edit/approval link directly to the manager's phone).*

### Step 2.4 — Set Schedule
- Set the trigger timer: **Every 15 minutes** (or every 30 minutes).
- Turn the scenario toggle to **ON**.

---

## 📬 Step 3 — Build Scenario 2 (Optional): Publish Manager-Approved Replies

When the manager reviews a 1–3 star draft and clicks **Approve** on the dashboard, this scenario posts the approved text to Google:

1. **Trigger:** **HTTP** -> **Make a request**
   - URL: `https://YOUR_BOT_DOMAIN_OR_IP/api/webhook/pending-replies`
   - Method: `GET`
   - Headers: `X-Webhook-Secret: <YOUR_SECRET>`
2. **Iterator Module:**
   - Array: `{{1.data.replies}}`
3. **Action:** **Google My Business** -> **Create/Update a Reply**
   - Review: `accounts/X/locations/Y/reviews/{{2.review_id}}`
   - Reply: `{{2.reply_text}}`
4. **Action:** **HTTP** -> **Make a request**
   - URL: `https://YOUR_BOT_DOMAIN_OR_IP/api/webhook/mark-posted`
   - Method: `POST`
   - Request content: `{"review_id": "{{2.review_id}}"}`
5. Set schedule: **Every 15 minutes**, turn toggle **ON**.

---

## 🎯 Verification Checklist

- [ ] Make.com scenario is saved and turned **ON**.
- [ ] `/health` on your bot returns `200 OK`.
- [ ] Test review payload posted to `/api/webhook/review-received` successfully creates an entry in `reviews.db`.
- [ ] 4–5 star test review generates an AI reply and returns `action: "reply"`.
- [ ] 1–3 star test review sends an alert to your Telegram chat and waits for approval.
