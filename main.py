import base64
import os
from email.mime.text import MIMEText
from google.oauth2 import service_account
from googleapiclient.discovery import build

EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT")

message_text = "JP Auto Sourcing Test Email"

message = MIMEText(message_text)

message["to"] = EMAIL_ACCOUNT
message["from"] = EMAIL_ACCOUNT
message["subject"] = "JP Sourcing Test"

raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

service = build("gmail", "v1")

body = {"raw": raw}

print("Email send simulation complete")
