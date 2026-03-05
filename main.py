import os
import smtplib
from email.mime.text import MIMEText

EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

print("JP Sourcing System Running")

message = MIMEText("JP Auto Sourcing Test Email")

message["Subject"] = "JP Sourcing Test"
message["From"] = EMAIL_ACCOUNT
message["To"] = EMAIL_ACCOUNT

server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()
server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)

server.sendmail(
    EMAIL_ACCOUNT,
    EMAIL_ACCOUNT,
    message.as_string()
)

server.quit()

print("Email sent successfully")
