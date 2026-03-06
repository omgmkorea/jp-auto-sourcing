import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime
import os

NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
def check_naver_products(keyword):

    url = "https://openapi.naver.com/v1/search/shop.json"

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }

    params = {
        "query": keyword,
        "display": 10
    }

    try:
        res = requests.get(url, headers=headers, params=params)
        data = res.json()

        total = data.get("total", 0)

        return total

    except:
        return 0
# ---------------------------
# 1️⃣ 이메일 설정
# ---------------------------
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

# 본인 이메일
TO_ADDRESS = EMAIL_ADDRESS

# ---------------------------
# 2️⃣ 오늘 날짜
# ---------------------------
today = datetime.now().strftime("%Y-%m-%d")

# ---------------------------
# 3️⃣ Amazon 카테고리
# ---------------------------
categories = {
    "ドラッグストア": "https://www.amazon.co.jp/gp/bestsellers/hpc",
    "ビューティー": "https://www.amazon.co.jp/gp/bestsellers/beauty",
    "文房具・オフィス用品": "https://www.amazon.co.jp/gp/bestsellers/office-products",
    "ホーム＆キッチン": "https://www.amazon.co.jp/gp/bestsellers/home",
    "食品": "https://www.amazon.co.jp/gp/bestsellers/food-beverage",
}

# ---------------------------
# 4️⃣ 상품 수집
# ---------------------------
all_products = []

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7"
}

for category, url in categories.items():

    try:

        response = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(response.text, "html.parser")

        items = soup.select(".zg-grid-general-faceout")

        for item in items[:10]:

            title = item.select_one("._cDEzb_p13n-sc-css-line-clamp-3_g3dy1")

            price = item.select_one(".p13n-sc-price")

            link = item.select_one("a")

            if title and link:

                title = title.text.strip()

                if price:
                    price = price.text.strip()
                else:
                    price = "가격 없음"

                link = "https://www.amazon.co.jp" + link.get("href")

                all_products.append({
                    "category": category,
                    "title": title,
                    "price": price,
                    "link": link,
                })

    except Exception as e:
        print("error:", e)


print("수집 상품 수:", len(all_products))


# ---------------------------
# 5️⃣ 이메일 내용 생성
# ---------------------------
body = "<h2>이번 주 추천 상품</h2><ul>"

for p in all_products:

    body += f'<li>[{p["category"]}] <a href="{p["link"]}">{p["title"]}</a> - {p["price"]}</li>'

body += "</ul>"


# ---------------------------
# 6️⃣ 이메일 발송
# ---------------------------
subject = f"Amazon 추천 상품 - {today}"

msg = MIMEText(body, "html", "utf-8")

msg["Subject"] = Header(subject, "utf-8")
msg["From"] = EMAIL_ADDRESS
msg["To"] = TO_ADDRESS


server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()
server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)

server.sendmail(
    EMAIL_ADDRESS,
    TO_ADDRESS,
    msg.as_string()
)

server.quit()


print("이메일 발송 완료")
