import base64
import os
import datetime
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

print("JP Sourcing System Running")

today = datetime.date.today()

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json", SCOPES
)

creds = flow.run_console()

service = build("gmail", "v1", credentials=creds)

message = MIMEText(f"JP sourcing system test\n\nDate: {today}")
message["to"] = os.getenv("EMAIL_ACCOUNT")
message["subject"] = "JP Auto Sourcing Test"

raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

service.users().messages().send(
    userId="me",
    body={"raw": raw}
).execute()

print("Email sent!")
