import os
import smtplib
from email.mime.text import MIMEText
import datetime

print("JP Sourcing System Running")

today = datetime.date.today()

EMAIL = os.getenv("EMAIL_ACCOUNT")

subject = "JP Auto Sourcing Test Email"
body = f"""
JP Sourcing System Test

Today's date: {today}

If you received this email, the automation system is working.
"""

msg = MIMEText(body)
msg["Subject"] = subject
msg["From"] = EMAIL
msg["To"] = EMAIL

server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()
server.login(EMAIL, os.getenv("EMAIL_PASSWORD"))
server.sendmail(EMAIL, EMAIL, msg.as_string())
server.quit()

print("Email sent successfully")
