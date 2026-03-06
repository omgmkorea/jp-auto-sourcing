import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import os
import csv
from deep_translator import GoogleTranslator

EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

today = datetime.now().strftime("%Y-%m-%d")

history_file = "products_history.csv"
result_file = "recommended_products.csv"

categories = {
    "ビューティー": "https://www.amazon.co.jp/gp/bestsellers/beauty",
    "ドラッグストア": "https://www.amazon.co.jp/gp/bestsellers/hpc",
    "ホーム＆キッチン": "https://www.amazon.co.jp/gp/bestsellers/home",
    "文房具": "https://www.amazon.co.jp/gp/bestsellers/office-products",
    "食品": "https://www.amazon.co.jp/gp/bestsellers/food-beverage"
}

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8"
}

ban_keywords = [
    "コンタクト",
    "contact lens",
    "リチウム",
    "battery",
    "knife",
    "ナイフ"
]

products = []

def translate_to_korean(text):

    try:
        result = GoogleTranslator(source='auto', target='ko').translate(text)
        return result
    except:
        return text

def make_smartstore_title(title_ko):

    words = title_ko.split()

    short = " ".join(words[:6])

    smart_title = short + " 일본 직구 정품"

    return smart_title

def collect_products():

    for category, url in categories.items():

        try:

            res = requests.get(url, headers=headers, timeout=20)

            soup = BeautifulSoup(res.text, "html.parser")

            items = soup.select(".zg-grid-general-faceout")

            for item in items[:50]:

                title = item.select_one("._cDEzb_p13n-sc-css-line-clamp-3_g3dy1")
                price = item.select_one(".p13n-sc-price")
                link = item.select_one("a")

                if not title or not link:
                    continue

                title = title.text.strip()

                if any(b in title.lower() for b in ban_keywords):
                    continue

                if price:
                    price = price.text.strip().replace("￥","").replace(",","")
                else:
                    price = "0"

                link = "https://www.amazon.co.jp" + link.get("href")

                review = item.select_one(".a-size-small")
                rating = item.select_one(".a-icon-alt")

                reviews = 0
                rating_val = 0

                if review:
                    try:
                        reviews = int(review.text.replace(",",""))
                    except:
                        pass

                if rating:
                    try:
                        rating_val = float(rating.text.split()[0])
                    except:
                        pass

                asin = link.split("/dp/")[1].split("/")[0]

                products.append({
                    "date": today,
                    "asin": asin,
                    "title": title,
                    "price": int(price),
                    "reviews": reviews,
                    "rating": rating_val,
                    "link": link
                })

        except Exception as e:

            print("error", e)

collect_products()

history = {}

if os.path.exists(history_file):

    with open(history_file, "r", encoding="utf-8") as f:

        reader = csv.DictReader(f)

        for row in reader:

            history[row["asin"]] = row

recommend = []

for p in products:

    asin = p["asin"]

    review_diff = 0
    price_changed = False

    if asin in history:

        old = history[asin]

        old_review = int(old["reviews"])
        old_price = int(old["price"])

        review_diff = p["reviews"] - old_review

        if p["price"] != old_price:
            price_changed = True

    if review_diff > 20 or price_changed:

        title_ko = translate_to_korean(p["title"])

        smart_title = make_smartstore_title(title_ko)

        recommend.append({
            "asin": asin,
            "title_jp": p["title"],
            "title_ko": title_ko,
            "smartstore_title": smart_title,
            "price": p["price"],
            "review_increase": review_diff,
            "link": p["link"]
        })

if recommend:

    with open(result_file, "w", newline="", encoding="utf-8-sig") as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "asin",
                "title_jp",
                "title_ko",
                "smartstore_title",
                "price",
                "review_increase",
                "link"
            ]
        )

        writer.writeheader()

        for r in recommend:

            writer.writerow(r)

with open(history_file, "w", newline="", encoding="utf-8-sig") as f:

    writer = csv.DictWriter(
        f,
        fieldnames=[
            "date",
            "asin",
            "title",
            "price",
            "reviews",
            "rating"
        ]
    )

    writer.writeheader()

    for p in products:

        writer.writerow({
            "date": p["date"],
            "asin": p["asin"],
            "title": p["title"],
            "price": p["price"],
            "reviews": p["reviews"],
            "rating": p["rating"]
        })

msg = MIMEMultipart()

msg["Subject"] = f"Amazon Japan 자동소싱 추천 - {today}"
msg["From"] = EMAIL_ADDRESS
msg["To"] = EMAIL_ADDRESS

body = "이번 주 Amazon Japan 급상승 상품을 확인하세요."

msg.attach(MIMEText(body, "plain"))

if os.path.exists(result_file):

    part = MIMEBase("application", "octet-stream")

    with open(result_file, "rb") as f:

        part.set_payload(f.read())

    encoders.encode_base64(part)

    part.add_header(
        "Content-Disposition",
        f"attachment; filename={result_file}"
    )

    msg.attach(part)

server = smtplib.SMTP("smtp.gmail.com", 587)

server.starttls()

server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)

server.sendmail(
    EMAIL_ADDRESS,
    EMAIL_ADDRESS,
    msg.as_string()
)

server.quit()

print("자동소싱 이메일 발송 완료")
