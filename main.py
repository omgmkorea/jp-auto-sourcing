import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from datetime import datetime, timedelta
import pandas as pd
import os
import time
import random
import logging
from deep_translator import GoogleTranslator

# ---------------------------
# 로깅 설정
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("sourcing.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ---------------------------
# 모드 설정
# TEST_MODE = True  → 가짜 7일치 데이터 자동 생성, 즉시 이메일 확인 가능
# TEST_MODE = False → 실제 누적 데이터 기반 운영 모드
# ---------------------------
TEST_MODE = True

# ---------------------------
# 이메일 설정
# ---------------------------
EMAIL_ADDRESS  = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
TO_ADDRESS     = EMAIL_ADDRESS

# ---------------------------
# 네이버 API
# ---------------------------
NAVER_CLIENT_ID     = os.environ.get("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")

# ---------------------------
# 소싱 조건 설정
# ---------------------------
REVIEW_SPIKE_THRESHOLD = 50   # 7일 내 리뷰 증가량 기준 (개)
NAVER_MAX_COUNT        = 0    # 네이버 검색결과 허용 최대 수 (0 = 완전 미등록만)
CRAWL_DELAY_MIN        = 2    # 요청 간 최소 딜레이 (초)
CRAWL_DELAY_MAX        = 5    # 요청 간 최대 딜레이 (초)

# ---------------------------
# 금지 키워드
# ---------------------------
BANNED_KEYWORDS = [
    "コンタクト", "contact lens",
    "リチウム", "lithium", "battery",
    "gun", "銃",
]

# ---------------------------
# Amazon JP 카테고리
# ---------------------------
CATEGORIES = {
    "ドラッグストア": "https://www.amazon.co.jp/gp/bestsellers/hpc",
    "ビューティー":   "https://www.amazon.co.jp/gp/bestsellers/beauty",
    "文房具":         "https://www.amazon.co.jp/gp/bestsellers/office-products",
    "ホーム":         "https://www.amazon.co.jp/gp/bestsellers/home",
    "食品":           "https://www.amazon.co.jp/gp/bestsellers/food-beverage",
}

# ---------------------------
# 히스토리 파일 경로
# ---------------------------
HISTORY_FILE = "review_history.csv"


# ============================================================
# 히스토리 관련 함수
# ============================================================

def load_history() -> pd.DataFrame:
    """저장된 리뷰 히스토리 로드. 없으면 빈 DataFrame 반환."""
    if os.path.exists(HISTORY_FILE):
        df = pd.read_csv(HISTORY_FILE)
        df["date"] = pd.to_datetime(df["date"])
        return df
    return pd.DataFrame(columns=["date", "asin", "title", "category", "price", "reviews", "link"])


def save_history(df: pd.DataFrame):
    """히스토리 저장 (최근 30일치만 유지)"""
    cutoff = datetime.now() - timedelta(days=30)
    df = df[df["date"] >= cutoff]
    df.to_csv(HISTORY_FILE, index=False)
    log.info(f"히스토리 저장 완료: {len(df)}건")


def inject_test_history(today_products: list) -> pd.DataFrame:
    """
    [테스트 모드 전용]
    오늘 수집한 상품 기반으로 7일 전 가짜 데이터 생성.
    리뷰수를 (현재 - 랜덤 증가분)으로 설정해서 급증 시뮬레이션.
    """
    log.info("[TEST MODE] 가짜 7일치 히스토리 데이터 생성 중...")
    fake_rows = []
    seven_days_ago = datetime.now() - timedelta(days=7)

    for p in today_products:
        current_reviews = parse_review_count(p["reviews"])
        # 절반은 급증 시뮬레이션 (리뷰 50~150개 증가), 절반은 변화 없음
        if random.random() > 0.5:
            past_reviews = max(0, current_reviews - random.randint(50, 150))
        else:
            past_reviews = current_reviews  # 증가 없음 → 필터에서 제외됨

        fake_rows.append({
            "date":     seven_days_ago,
            "asin":     extract_asin(p["link"]),
            "title":    p["title"],
            "category": p["category"],
            "price":    p["price"],
            "reviews":  str(past_reviews),
            "link":     p["link"],
        })

    df_fake = pd.DataFrame(fake_rows)
    log.info(f"[TEST MODE] 가짜 히스토리 {len(df_fake)}건 생성 완료")
    return df_fake


# ============================================================
# 유틸 함수
# ============================================================

def parse_review_count(review_str: str) -> int:
    """리뷰 문자열 → 정수 변환 (예: '1,234' → 1234)"""
    try:
        return int(str(review_str).replace(",", "").strip())
    except:
        return 0


def extract_asin(link: str) -> str:
    """상품 링크에서 ASIN 추출"""
    try:
        parts = link.split("/dp/")
        if len(parts) > 1:
            return parts[1].split("/")[0].split("?")[0]
    except:
        pass
    return link  # 추출 실패 시 링크 자체를 ID로 사용


def is_banned(title: str) -> bool:
    """금지 키워드 포함 여부 확인"""
    title_lower = title.lower()
    return any(b.lower() in title_lower for b in BANNED_KEYWORDS)


# ============================================================
# 번역 / 제목 생성
# ============================================================

def translate_to_korean(text: str) -> str:
    try:
        return GoogleTranslator(source="ja", target="ko").translate(text)
    except Exception as e:
        log.warning(f"번역 실패: {e}")
        return text


def create_korean_title(title: str) -> str:
    translated = translate_to_korean(title)
    return f"일본 정품 {translated}"


# ============================================================
# 네이버 쇼핑 API
# ============================================================

def naver_search(keyword: str) -> int:
    """네이버 쇼핑 검색 결과 수 반환. 실패 시 -1 반환."""
    url = "https://openapi.naver.com/v1/search/shop.json"
    headers = {
        "X-Naver-Client-Id":     NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": 1}

    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        res.raise_for_status()
        return res.json().get("total", 0)
    except Exception as e:
        log.warning(f"네이버 API 오류 ({keyword}): {e}")
        return -1  # -1 = API 오류 (필터에서 제외하지 않음)


# ============================================================
# Amazon JP 크롤링
# ============================================================

CRAWL_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja-JP,ja;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def crawl_category(category: str, url: str) -> list:
    """카테고리 베스트셀러 1~30위 크롤링"""
    products = []

    try:
        time.sleep(random.uniform(CRAWL_DELAY_MIN, CRAWL_DELAY_MAX))
        res = requests.get(url, headers=CRAWL_HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select(".zg-grid-general-faceout")

        if not items:
            log.warning(f"[{category}] 상품 항목을 찾지 못했습니다. 셀렉터 확인 필요.")
            return []

        log.info(f"[{category}] {len(items)}개 항목 발견")

        for rank, item in enumerate(items[:30], start=1):  # 1~30위만
            # 제목 (여러 셀렉터 시도)
            title_el = (
                item.select_one("._cDEzb_p13n-sc-css-line-clamp-3_g3dy1")
                or item.select_one(".p13n-sc-truncate-desktop-type2")
                or item.select_one(".p13n-sc-truncate")
            )
            if not title_el:
                continue

            title = title_el.text.strip()

            if is_banned(title):
                log.info(f"금지 키워드 포함, 스킵: {title[:30]}")
                continue

            price_el  = item.select_one(".p13n-sc-price")
            link_el   = item.select_one("a")
            review_el = item.select_one(".a-size-small")

            price   = price_el.text.strip() if price_el else ""
            reviews = review_el.text.strip().replace(",", "") if review_el else "0"
            link    = ("https://amazon.co.jp" + link_el.get("href")) if link_el else ""

            products.append({
                "category": category,
                "rank":     rank,
                "title":    title,
                "price":    price,
                "reviews":  reviews,
                "link":     link,
                "asin":     extract_asin(link),
            })

    except Exception as e:
        log.error(f"[{category}] 크롤링 오류: {e}")

    return products


def crawl_all() -> list:
    """전체 카테고리 크롤링"""
    all_products = []
    for category, url in CATEGORIES.items():
        log.info(f"크롤링 시작: {category}")
        products = crawl_category(category, url)
        all_products.extend(products)
        log.info(f"[{category}] {len(products)}개 수집")
    log.info(f"전체 수집 완료: {len(all_products)}개")
    return all_products


# ============================================================
# 리뷰 급증 감지
# ============================================================

def detect_review_spikes(today_products: list, history_df: pd.DataFrame) -> list:
    """
    7일 전 리뷰수와 오늘 리뷰수를 비교하여 급증 상품 필터링.
    증가량이 REVIEW_SPIKE_THRESHOLD 이상인 상품만 반환.
    """
    if history_df.empty:
        log.warning("히스토리 데이터 없음. 7일 후부터 급증 감지 가능.")
        return []

    seven_days_ago = datetime.now() - timedelta(days=7)
    # 7일 전 ±1일 범위의 데이터
    old_df = history_df[
        (history_df["date"] >= seven_days_ago - timedelta(days=1)) &
        (history_df["date"] <= seven_days_ago + timedelta(days=1))
    ]

    if old_df.empty:
        log.warning("7일 전 데이터 없음. 데이터 누적 중...")
        return []

    # ASIN 기준으로 7일 전 리뷰수 딕셔너리 생성
    old_reviews = dict(zip(old_df["asin"], old_df["reviews"].apply(parse_review_count)))

    spiked = []
    for p in today_products:
        asin           = p["asin"]
        current_count  = parse_review_count(p["reviews"])
        past_count     = old_reviews.get(asin)

        if past_count is None:
            continue  # 7일 전 데이터 없는 신규 상품은 스킵

        increase = current_count - past_count

        if increase >= REVIEW_SPIKE_THRESHOLD:
            p["review_increase"] = increase
            p["past_reviews"]    = past_count
            spiked.append(p)
            log.info(f"리뷰 급증 감지: {p['title'][:30]} (+{increase}개)")

    log.info(f"급증 상품: {len(spiked)}개")
    return spiked


# ============================================================
# 네이버 미등록 필터
# ============================================================

def filter_naver_unlisted(products: list) -> list:
    """네이버 쇼핑 미등록 상품만 필터링"""
    unlisted = []
    for p in products:
        korean_title = create_korean_title(p["title"])
        p["korean_title"] = korean_title

        count = naver_search(korean_title)
        time.sleep(0.5)  # API 호출 간 딜레이

        if count == -1:
            log.warning(f"네이버 API 오류, 스킵: {korean_title[:30]}")
            continue

        if count <= NAVER_MAX_COUNT:
            p["naver_count"] = count
            unlisted.append(p)
            log.info(f"블루오션 발굴: {korean_title[:30]} (네이버 {count}건)")
        else:
            log.info(f"네이버 등록됨({count}건), 스킵: {korean_title[:30]}")

    log.info(f"네이버 미등록 상품: {len(unlisted)}개")
    return unlisted


# ============================================================
# 이메일 발송
# ============================================================

def build_email_body(products: list, is_test: bool) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    test_badge = '<span style="background:#ff6b35;color:white;padding:2px 8px;border-radius:4px;font-size:12px;">TEST MODE</span>' if is_test else ""

    body = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:800px;margin:0 auto;">
    <h2 style="color:#232f3e;">🛒 Amazon JP 자동소싱 리포트 {test_badge}</h2>
    <p style="color:#666;">{today} 기준 | 리뷰 급증(+{REVIEW_SPIKE_THRESHOLD}개↑) + 네이버 미등록 상품</p>
    <hr>
    """

    if not products:
        body += "<p>⚠️ 조건에 맞는 상품이 없습니다.</p>"
    else:
        body += f"<p><strong>총 {len(products)}개 상품 발굴</strong></p>"
        for i, p in enumerate(products, 1):
            increase = p.get("review_increase", "N/A")
            past     = p.get("past_reviews", "N/A")
            current  = parse_review_count(p["reviews"])

            body += f"""
            <div style="border:1px solid #ddd;border-radius:8px;padding:16px;margin:12px 0;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="background:#232f3e;color:white;padding:2px 8px;border-radius:4px;font-size:12px;">#{i} {p['category']}</span>
                <span style="color:#e47911;font-weight:bold;">베스트셀러 {p.get('rank','?')}위</span>
              </div>
              <h3 style="margin:8px 0;color:#0f1111;">{p['korean_title']}</h3>
              <p style="color:#666;font-size:13px;margin:4px 0;">원제: {p['title']}</p>
              <div style="display:flex;gap:16px;margin:8px 0;flex-wrap:wrap;">
                <span>💴 <strong>{p['price']}</strong></span>
                <span>📝 리뷰 {past}→{current} (<span style="color:green;font-weight:bold;">+{increase}개/7일</span>)</span>
                <span>🔍 네이버 {p.get('naver_count',0)}건</span>
              </div>
              <a href="{p['link']}" style="background:#ff9900;color:white;padding:8px 16px;border-radius:4px;text-decoration:none;font-size:14px;">Amazon 상품 보기 →</a>
            </div>
            """

    body += """
    <hr>
    <p style="color:#999;font-size:12px;">본 메일은 자동발송입니다.</p>
    </body></html>
    """
    return body


def send_email(products: list, csv_path: str, is_test: bool):
    today    = datetime.now().strftime("%Y-%m-%d")
    subject  = f"[{'TEST' if is_test else '실전'}] Amazon 자동소싱 {today} - {len(products)}개 발굴"
    body     = build_email_body(products, is_test)

    msg = MIMEMultipart()
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = EMAIL_ADDRESS
    msg["To"]      = TO_ADDRESS
    msg.attach(MIMEText(body, "html", "utf-8"))

    # CSV 첨부
    if os.path.exists(csv_path):
        with open(csv_path, "rb") as f:
            attach = MIMEApplication(f.read())
        attach.add_header("Content-Disposition", "attachment", filename=os.path.basename(csv_path))
        msg.attach(attach)

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, TO_ADDRESS, msg.as_string())
        server.quit()
        log.info(f"이메일 발송 완료: {subject}")
    except Exception as e:
        log.error(f"이메일 발송 실패: {e}")


# ============================================================
# 메인 실행
# ============================================================

def main():
    today     = datetime.now().strftime("%Y-%m-%d")
    log.info(f"========== 소싱 시작 ({today}) | 모드: {'TEST' if TEST_MODE else '실전'} ==========")

    # 1. Amazon JP 크롤링
    today_products = crawl_all()
    if not today_products:
        log.error("수집된 상품 없음. 종료.")
        return

    # 2. 히스토리 로드
    history_df = load_history()

    # 3. 테스트 모드: 가짜 7일치 데이터 주입
    if TEST_MODE:
        fake_history = inject_test_history(today_products)
        history_df   = pd.concat([history_df, fake_history], ignore_index=True)

    # 4. 오늘 데이터를 히스토리에 추가 & 저장
    today_df = pd.DataFrame([{
        "date":     datetime.now(),
        "asin":     p["asin"],
        "title":    p["title"],
        "category": p["category"],
        "price":    p["price"],
        "reviews":  p["reviews"],
        "link":     p["link"],
    } for p in today_products])
    save_history(pd.concat([history_df, today_df], ignore_index=True))

    # 5. 리뷰 급증 감지
    spiked_products = detect_review_spikes(today_products, history_df)

    if not spiked_products:
        log.info("리뷰 급증 상품 없음. 이메일 미발송.")
        return

    # 6. 네이버 미등록 필터
    final_products = filter_naver_unlisted(spiked_products)

    # 7. CSV 저장
    csv_name = f"amazon_sourcing_{today}{'_test' if TEST_MODE else ''}.csv"
    df_out   = pd.DataFrame(final_products)
    df_out.to_csv(csv_name, index=False, encoding="utf-8-sig")
    log.info(f"CSV 저장: {csv_name} ({len(final_products)}건)")

    # 8. 이메일 발송
    send_email(final_products, csv_name, is_test=TEST_MODE)

    log.info("========== 소싱 완료 ==========")


if __name__ == "__main__":
    main()
