import os
import requests
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv()

SCOPES        = ["https://www.googleapis.com/auth/business.manage"]
LOCATION_NAME = os.getenv("GBP_LOCATION_NAME")  # accounts/X/locations/Y
TOKEN_FILE    = os.getenv("TOKEN_FILE", "/etc/secrets/token.json" if os.path.exists("/etc/secrets") else "token.json")
CREDS_FILE    = "credentials.json"   # Downloaded from Google Cloud Console


def get_credentials():
    """
    Load token.json if it exists.
    Auto-refresh if expired.
    First run only: opens browser to log in with restaurant Google account.
    After that: fully automatic, no human needed.
    """
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Auto-refresh expired token using refresh_token (no login needed)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        return creds

    # First-time only: browser login
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


def _auth_headers():
    creds = get_credentials()
    return {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type":  "application/json"
    }


def fetch_reviews():
    """
    Fetch all reviews for your restaurant from the GBP API.
    Handles pagination automatically.
    Returns list of raw review dicts.
    """
    url        = f"https://mybusiness.googleapis.com/v4/{LOCATION_NAME}/reviews"
    all_reviews = []
    page_token  = None

    while True:
        params = {"pageSize": 50}
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(url, headers=_auth_headers(), params=params)
        resp.raise_for_status()
        data = resp.json()

        all_reviews.extend(data.get("reviews", []))

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return all_reviews


def post_reply(review_name: str, reply_text: str):
    """
    Post owner reply to a review.
    review_name = accounts/X/locations/Y/reviews/Z
    Returns (success: bool, message: str)
    """
    url     = f"https://mybusiness.googleapis.com/v4/{review_name}/reply"
    payload = {"comment": reply_text}

    resp = requests.put(url, headers=_auth_headers(), json=payload)

    if resp.status_code == 200:
        return True, "OK"
    else:
        return False, f"HTTP {resp.status_code}: {resp.text}"
