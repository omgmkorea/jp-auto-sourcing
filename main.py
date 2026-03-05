import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import os

# ---------------------------
# 날짜 설정
# ---------------------------
today = datetime.now()
today_str = today.strftime("%Y-%m-%d")
one_week_ago = today - timedelta(days=7)
one_week_ago_str = one_week_ago.strftime("%Y-%m-%d")

# ---------------------------
# Amazon JP 카테고리
# ---------------------------
categories = {
    "영양제": "ドラッグストア",
    "화장품": "ビューティー",
    "문구류": "文房具・オフィス用品",
    "생활용품": "ホーム＆キッチン",
    "식품": "食品"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "ja-JP,ja;q=0.9"
}

# 데이터 저장용 CSV
DATA_FILE = "amazon_weekly.csv"

# ---------------------------
# 1. 이번주 상품 수집
# ---------------------------
weekly_products = []

for cat_name, cat_jp in categories.items():
    URL = f"https://www.amazon.co.jp/s?k={cat_jp}"
    response = requests.get(URL, headers=HEADERS)
    soup = BeautifulSoup(response.text, "lxml")

    items = soup.select("div.s-main-slot div.s-result-item")
    
    for item in items[:50]:  # 상위 50개 정도 검사
        # 제목
        title_tag = item.select_one("span.a-text-normal")
        if not title_tag:
            continue
        title = title_tag.get_text().strip()

        # 링크
        link_tag = item.select_one("a.a-link-normal")
        if link_tag and 'href' in link_tag.attrs:
            link = "https://www.amazon.co.jp" + link_tag['href']
        else:
            link = ""

        # 가격
        price_tag = item.select_one("span.a-price > span.a-offscreen")
        if not price_tag:
            continue
        price_text = price_tag.get_text().replace("￥", "").replace(",", "").strip()
        try:
            price = int(price_text)
        except:
            continue
        if price < 800 or price > 20000:
            continue  # 가격 필터

        # 랭킹 100위 밖 확인
        # 참고: 일반 페이지 크롤링만으로 정확한 랭킹은 어렵지만, 상위 N개만 제외 처리 가능
        # 여기서는 상위 10개 정도 제외 (임시)
        rank_tag = item.get('data-index')
        if rank_tag and int(rank_tag) <= 10:
            continue

        # 리뷰 수
        review_tag = item.select_one("span.a-size-base")
        if review_tag:
            try:
                reviews = int(review_tag.get_text().replace(",", ""))
            except:
                reviews = 0
        else:
            reviews = 0

        weekly_products.append({
            "date": today_str,
            "category": cat_name,
            "title": title,
            "link": link,
            "price": price,
            "reviews": reviews
        })

# ---------------------------
# 2. 과거 데이터와 비교 (리뷰 증가율 계산)
# ---------------------------
# CSV 파일 읽기
past_products = {}
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row['link']
            past_products[key] = int(row['reviews'])

# 리뷰 증가량 계산
recommended = []
for prod in weekly_products:
    prev_reviews = past_products.get(prod['link'], 0)
    if prod['reviews'] - prev_reviews >= 5:  # 일주일 동안 리뷰 5개 이상 증가
        recommended.append(prod)

# ---------------------------
# 3. CSV 업데이트
# ---------------------------
with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
    fieldnames = ["date", "category", "title", "link", "price", "reviews"]
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for prod in weekly_products:
        writer.writerow(prod)

# ---------------------------
# 4. 이메일 내용
# ---------------------------
email_body = f"{today_str} Amazon Japan 주간 추천 상품:\n\n"
for prod in recommended:
    email_body += f"[{prod['category']}] {prod['title']} - {prod['price']}円\n{prod['link']}\n\n"

if not recommended:
    email_body += "이번 주 추천 상품이 없습니다."

# ---------------------------
# 5. 이메일 발송
# ---------------------------
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_ADDRESS = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"
TO_ADDRESS = "받는사람@gmail.com"

msg = MIMEText(email_body)
msg["Subject"] = f"Amazon Japan 주간 추천 상품 ({today_str})"
msg["From"] = EMAIL_ADDRESS
msg["To"] = TO_ADDRESS

with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
    server.starttls()
    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    server.send_message(msg)

print("주간 추천 이메일 발송 완료! ✅")
