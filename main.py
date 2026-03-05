import os
import base64
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT")

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json", SCOPES
)

creds = flow.run_local_server(port=0)

service = build("gmail", "v1", credentials=creds)

message = MIMEText("JP Auto Sourcing Test Email")

message["to"] = EMAIL_ACCOUNT
message["from"] = EMAIL_ACCOUNT
message["subject"] = "JP Sourcing Test"

raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

body = {"raw": raw}

service.users().messages().send(
    userId="me",
    body=body
).execute()

print("Email sent successfully")
