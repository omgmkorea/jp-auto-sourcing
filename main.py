import datetime
import smtplib
from email.mime.text import MIMEText
import os

print("JP Sourcing System Running")

# 오늘 날짜
today = datetime.date.today()

# 이메일 내용
message = f"""
JP Sourcing Daily Report

Today's date: {today}

System test email.
"""

# 환경변수 (GitHub Secrets)
EMAIL_ACCOUNT = os.getenv("EMAIL_ACCOUNT")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# 이메일 만들기
msg = MIMEText(message)
msg['Subject'] = "JP Auto Sourcing Test"
msg['From'] = EMAIL_ACCOUNT
msg['To'] = EMAIL_ACCOUNT

# Gmail SMTP 서버 연결
server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()

server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)

server.send_message(msg)

server.quit()

print("Email sent successfully")
