import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
import os

print("JP Auto Sourcing Start")

EMAIL_ACCOUNT = os.environ.get("EMAIL_ACCOUNT")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

url = "https://www.amazon.co.jp/gp/bestsellers"

headers = {
    "User-Agent": "Mozilla/5.0"
}

res = requests.get(url, headers=headers)
soup = BeautifulSoup(res.text, "html.parser")

products = soup.select("._cDEzb_p13n-sc-css-line-clamp-3_g3dy1")

results = []

for p in products[:10]:
    title = p.text.strip()
    results.append(title)

message = "🔥 일본 아마존 인기 상품\n\n"

for r in results:
    message += f"- {r}\n"

print(message)

msg = MIMEText(message)
msg["Subject"] = "JP Auto Sourcing Result"
msg["From"] = EMAIL_ACCOUNT
msg["To"] = EMAIL_ACCOUNT

server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()
server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
server.send_message(msg)
server.quit()

print("Email sent successfully")
