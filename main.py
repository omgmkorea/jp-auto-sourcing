import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

# ---------------------------
# 1. Amazon 상품 수집
# ---------------------------
URL = "https://www.amazon.co.jp/s?k=toy"  # 예시: 장난감 검색
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "ja-JP,ja;q=0.9"
}

response = requests.get(URL, headers=HEADERS)
soup = BeautifulSoup(response.text, "lxml")

items = soup.select("span.a-text-normal")  # 상품 제목
product_list = [item.get_text().strip() for item in items[:10]]  # 상위 10개만 예시

# ---------------------------
# 2. 이메일 내용 만들기
# ---------------------------
today = datetime.now().strftime("%Y-%m-%d")
email_body = f"{today} Amazon 상품 리스트:\n\n"
email_body += "\n".join(product_list)

# ---------------------------
# 3. 이메일 보내기
# ---------------------------
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_ADDRESS = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"  # Gmail 앱 비밀번호 사용

msg = MIMEText(email_body)
msg["Subject"] = f"오늘의 Amazon 상품 리스트 ({today})"
msg["From"] = EMAIL_ADDRESS
msg["To"] = "받는사람@gmail.com"

with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
    server.starttls()
    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    server.send_message(msg)

print("이메일 발송 완료!")
