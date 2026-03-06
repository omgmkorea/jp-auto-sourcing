import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from datetime import datetime
import pandas as pd
import os
from deep_translator import GoogleTranslator

# ---------------------------
# 이메일 설정
# ---------------------------
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
TO_ADDRESS = EMAIL_ADDRESS

# ---------------------------
# 네이버 API
# ---------------------------
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")

# ---------------------------
# 금지 키워드
# ---------------------------
banned_keywords = [
    "コンタクト",
    "contact lens",
    "リチウム",
    "battery",
    "gun",
]

# ---------------------------
# Amazon 카테고리
# ---------------------------
categories = {
    "ドラッグストア": "https://www.amazon.co.jp/gp/bestsellers/hpc",
    "ビューティー": "https://www.amazon.co.jp/gp/bestsellers/beauty",
    "文房具": "https://www.amazon.co.jp/gp/bestsellers/office-products",
    "ホーム": "https://www.amazon.co.jp/gp/bestsellers/home",
    "食品": "https://www.amazon.co.jp/gp/bestsellers/food-beverage"
}

# ---------------------------
# 네이버 검색
# ---------------------------
def naver_search(keyword):

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

        return data.get("total",0)

    except:
        return 999

# ---------------------------
# 번역
# ---------------------------
def translate_to_korean(text):

    try:

        result = GoogleTranslator(
            source='ja',
            target='ko'
        ).translate(text)

        return result

    except:

        return text

# ---------------------------
# 스마트스토어 상품명 생성
# ---------------------------
def create_korean_title(title):

    translated = translate_to_korean(title)

    smart_title = f"일본 정품 {translated}"

    return smart_title

# ---------------------------
# Amazon 상품 수집
# ---------------------------
headers = {
    "User-Agent":"Mozilla/5.0"
}

all_products = []

for category,url in categories.items():

    try:

        res = requests.get(url,headers=headers)

        soup = BeautifulSoup(res.text,"html.parser")

        items = soup.select(".zg-grid-general-faceout")

        rank = 0

        for item in items:

            rank += 1

            if rank < 50:
                continue

            title = item.select_one("._cDEzb_p13n-sc-css-line-clamp-3_g3dy1")

            price = item.select_one(".p13n-sc-price")

            link = item.select_one("a")

            review = item.select_one(".a-size-small")

            if not title:
                continue

            title = title.text.strip()

            if any(b in title.lower() for b in banned_keywords):
                continue

            if price:
                price = price.text.strip()
            else:
                price = ""

            if review:
                review = review.text.strip().replace(",","")
            else:
                review = "0"

            link = "https://amazon.co.jp" + link.get("href")

            # 한국어 번역
            korean_title = create_korean_title(title)

            # 네이버 검색
            naver_count = naver_search(korean_title)

            if naver_count != 0:
                continue

            all_products.append({

                "category":category,
                "title":title,
                "korean_title":korean_title,
                "price":price,
                "reviews":review,
                "link":link

            })

    except Exception as e:

        print("error:",e)

print("수집 상품:",len(all_products))

# ---------------------------
# CSV 생성
# ---------------------------
today = datetime.now().strftime("%Y-%m-%d")

df = pd.DataFrame(all_products)

csv_name = f"amazon_sourcing_{today}.csv"

df.to_csv(csv_name,index=False)

# ---------------------------
# 이메일 생성
# ---------------------------
body = "<h2>Amazon 자동소싱 추천 상품</h2><ul>"

for p in all_products:

    body += f'<li>{p["korean_title"]} - {p["price"]} <a href="{p["link"]}">상품보기</a></li>'

body += "</ul>"

msg = MIMEMultipart()

msg["Subject"] = Header(f"Amazon 자동소싱 {today}", "utf-8")
msg["From"] = EMAIL_ADDRESS
msg["To"] = TO_ADDRESS

msg.attach(MIMEText(body,"html","utf-8"))

# CSV 첨부
with open(csv_name,"rb") as f:

    attach = MIMEApplication(f.read())

attach.add_header(
    "Content-Disposition",
    "attachment",
    filename=csv_name
)

msg.attach(attach)

# ---------------------------
# 이메일 발송
# ---------------------------
server = smtplib.SMTP("smtp.gmail.com",587)
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
