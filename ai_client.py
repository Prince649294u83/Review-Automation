import os
from groq import Groq
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL  = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# ── Restaurant personality prompt ─────────────────────
SYSTEM_PROMPT = """
You are the owner of CRG Meridian Restaurant in Madikeri, Karnataka, India.
You personally read every review left on Google Maps and reply thoughtfully.

Rules for every reply:
1. Length: 40 to 70 words — never longer, never shorter
2. Tone: warm, genuine, personal — like a real owner who cares deeply
3. Be specific: reference something the reviewer actually mentioned
4. Vary your openings every time — never repeat the same first line
5. NEVER use these cliché phrases:
   - "Thank you for your feedback"
   - "Dear valued customer"
   - "We value your patronage"
   - "We look forward to serving you"
6. For 4-5 star reviews: express genuine gratitude, reference something
   specific they mentioned, invite them back warmly
7. For 1-3 star reviews: sincerely apologize, take responsibility,
   invite them to reach out to you directly (give an email or ask them
   to message you), never be defensive or make excuses
8. End with a warm sign-off like:
   "– The CRG Meridian Team" or "Warm regards from our kitchen 🙏"
9. Sound like a human, not a chatbot
"""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception)
)
def generate_reply(reviewer_name: str, star_rating: int, comment: str) -> str:
    """
    Generate a unique, human-sounding owner reply using Groq (free).
    Retries up to 3 times with exponential backoff on any API error.
    """
    # Handle star-only reviews with no text
    if not comment or not comment.strip():
        comment = f"[Customer left {star_rating} stars but no written comment]"

    stars_visual = "⭐" * star_rating

    user_message = f"""
Reviewer Name : {reviewer_name}
Star Rating   : {stars_visual} ({star_rating} out of 5)
Their Review  : "{comment}"

Write a reply from the restaurant owner. Follow all rules in the system prompt.
Vary your language — this should sound like a fresh, personal message.
"""

    response = client.chat.completions.create(
        model    = MODEL,
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message}
        ],
        temperature = 0.85,   # Enough variety so replies never sound copy-pasted
        max_tokens  = 180,
        top_p       = 0.9,
    )

    return response.choices[0].message.content.strip()
