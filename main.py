import datetime
import os

print("JP Sourcing System Running")

today = datetime.date.today()

email = os.getenv("EMAIL_ACCOUNT")

print(f"Today's date: {today}")
print(f"Email will be sent to: {email}")

print("System ready for Gmail API send")
