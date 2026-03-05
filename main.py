# main.py

import os
import requests
from bs4 import BeautifulSoup
import csv
import datetime
import smtplib
from email.mime.text import MIMEText

# ---------------------------
# 1️⃣ 환경 변수로 이메일 정보 가져오기
# ---------------------------
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
TO_ADDRESS = EMAIL_ADDRESS  # 수신자 이메일

# ---------------------------
# 2️⃣ Amazon JP 카테고리 및 URL 설정
# ---------------------------
CATEGORIES = {
    "ドラッグストア": "https://www.amazon.co.jp/s?i=drugstore",
    "ビューティー": "https://www.amazon.co.jp/s?i=beauty",
    "文房具・オフィス用品": "https://www.amazon.co.jp/s?i=office",
    "ホーム＆キッチン": "https://www.amazon.co.jp/s?i=home",
    "食品": "https://www.amazon.co.jp/s?i=gourmet"
}

# 상품 조건
MIN_PRICE = 800
MAX_PRICE = 20000

# ---------------------------
# 3️⃣ 상품 수집 함수
# ---------------------------
def get_products(category_name, url):
    products = []
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "lxml")
    
    # 여기서 상품 리스트 파싱
    for item in soup.select("div.s-result-item"):
        title_tag = item.select_one("h2 a span")
        link_tag = item.select_one("h2 a")
        price_tag = item.select_one(".a-price .a-offscreen")
        reviews_tag = item.select_one(".a-size-small .a-link-normal")
        
        if not (title_tag and link_tag and price_tag and reviews_tag):
            continue
        
        title = title_tag.get_text(strip=True)
        link = "https://www.amazon.co.jp" + link_tag.get("href")
        price_text = price_tag.get_text(strip=True).replace("￥","").replace(",","")
        price = int(price_text)
        reviews = int(reviews_tag.get_text(strip=True).replace(",",""))
        
        if MIN_PRICE <= price <= MAX_PRICE:
            products.append({
                "title": title,
                "link": link,
                "price": price,
                "reviews": reviews,
                "category": category_name
            })
    
    return products

# ---------------------------
# 4️⃣ 전체 카테고리 수집
# ---------------------------
all_products = []
for cat_name, url in CATEGORIES.items():
    all_products += get_products(cat_name, url)

# ---------------------------
# 5️⃣ CSV 저장
# ---------------------------
today = datetime.date.today()
csv_filename = f"amazon_weekly_{today}.csv"

with open(csv_filename, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["category","title","link","price","reviews"])
    writer.writeheader()
    for p in all_products:
        writer.writerow(p)

# ---------------------------
from email.header import Header

# 6️⃣ 이메일 발송
# ---------------------------
subject = f"주간 Amazon 추천 상품 - {today}"
body = "<h2>이번 주 추천 상품</h2><ul>"
for p in all_products:
    body += f'<li>[{p["category"]}] <a href="{p["link"]}">{p["title"]}</a> - {p["price"]}円, 리뷰: {p["reviews"]}</li>'
body += "</ul>"

msg = MIMEText(body, "html", "utf-8")
msg["Subject"] = Header(subject, "utf-8")
msg["From"] = EMAIL_ADDRESS
msg["To"] = TO_ADDRESS

server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()
server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
server.sendmail(EMAIL_ADDRESS, [TO_ADDRESS], msg.as_string())
server.quit()

print(f"주간 소싱 완료: {len(all_products)}개 상품 이메일 발송")
