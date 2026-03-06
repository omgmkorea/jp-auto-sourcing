import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime
import os
import re

# ---------------------------
# 1️⃣ 환경변수
# ---------------------------
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")

TO_ADDRESS = EMAIL_ADDRESS

# ---------------------------
# 2️⃣ 오늘 날짜
# ---------------------------
today = datetime.now().strftime("%Y-%m-%d")

# ---------------------------
# 3️⃣ Amazon 카테고리
# ---------------------------
categories = {
    "ドラッグストア": "https://www.amazon.co.jp/gp/bestsellers/hpc/ref=zg_bs_pg_3?pg=3",
    "ビューティー": "https://www.amazon.co.jp/gp/bestsellers/beauty/ref=zg_bs_pg_3?pg=3",
    "文房具・オフィス用品": "https://www.amazon.co.jp/gp/bestsellers/office-products/ref=zg_bs_pg_3?pg=3",
    "ホーム＆キッチン": "https://www.amazon.co.jp/gp/bestsellers/home/ref=zg_bs_pg_3?pg=3",
    "食品": "https://www.amazon.co.jp/gp/bestsellers/food-beverage/ref=zg_bs_pg_3?pg=3",
}

# ---------------------------
# 4️⃣ 반입금지 필터
# ---------------------------
banned_keywords = [
    "コンタクト", "contact lens",
    "laser", "weapon",
]

# ---------------------------
# 5️⃣ Google 번역
# ---------------------------
def translate_to_korean(text):

    url = "https://translate.googleapis.com/translate_a/single"

    params = {
        "client": "gtx",
        "sl": "ja",
        "tl": "ko",
        "dt": "t",
        "q": text
    }

    try:
        res = requests.get(url, params=params)
        result = res.json()
        return result[0][0][0]

    except:
        return text


# ---------------------------
# 6️⃣ 네이버 쇼핑 검색
# ---------------------------
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
# 7️⃣ 상품 수집
# ---------------------------
headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8"
}

all_products = []

for category, url in categories.items():

    try:

        response = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(response.text, "html.parser")

        items = soup.select(".zg-grid-general-faceout")

        for item in items:

            title_tag = item.select_one("._cDEzb_p13n-sc-css-line-clamp-3_g3dy1")
            price_tag = item.select_one(".p13n-sc-price")
            link_tag = item.select_one("a")

            if not title_tag or not link_tag or not price_tag:
                continue

            title = title_tag.text.strip()
            price_text = price_tag.text.strip()

            # 가격 숫자 추출
            price_number = int(re.sub(r"[^\d]", "", price_text))

            # 가격 필터
            if price_number < 800 or price_number > 20000:
                continue

            # 반입금지 필터
            banned = False
            for b in banned_keywords:
                if b.lower() in title.lower():
                    banned = True

            if banned:
                continue

            link = "https://www.amazon.co.jp" + link_tag.get("href")

            # 한국어 번역
            korean_title = translate_to_korean(title)

            # 네이버 검색
            naver_count = check_naver_products(korean_title)

            # 네이버에 존재하면 제외
            if naver_count != 0:
                continue

            all_products.append({
                "category": category,
                "title": korean_title,
                "price": price_text,
                "link": link
            })

    except Exception as e:

        print("error:", e)


print("수집 상품 수:", len(all_products))


# ---------------------------
# 8️⃣ 이메일 내용
# ---------------------------
body = "<h2>이번 주 Amazon 미판매 추천상품</h2><ul>"

for p in all_products:

    body += f'<li>[{p["category"]}] <a href="{p["link"]}">{p["title"]}</a> - {p["price"]}</li>'

body += "</ul>"


# ---------------------------
# 9️⃣ 이메일 발송
# ---------------------------
subject = f"Amazon Japan 소싱 리포트 - {today}"

msg = MIMEText(body, "html", "utf-8")

msg["Subject"] = Header(subject, "utf-8")
msg["From"] = EMAIL_ADDRESS
msg["To"] = TO_ADDRESS


server = smtplib.SMTP("smtp.gmail.com", 587)
server.starttls()

server.login(
    EMAIL_ADDRESS,
    EMAIL_PASSWORD
)

server.sendmail(
    EMAIL_ADDRESS,
    TO_ADDRESS,
    msg.as_string()
)

server.quit()

print("이메일 발송 완료")
