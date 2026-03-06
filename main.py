import re
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
import json
from deep_translator import GoogleTranslator
import gspread
from google.oauth2.service_account import Credentials

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
TEST_MODE = False

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
# Google Sheets 설정
# ---------------------------
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS")  # JSON 문자열
SPREADSHEET_NAME        = "amazon_sourcing_history"              # 시트 이름 (구글드라이브에서 생성 필요)
WORKSHEET_NAME          = "history"

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


# ============================================================
# [개선 1] Google Sheets 히스토리 관리
# ============================================================

def get_gspread_client():
    """Google Sheets 클라이언트 초기화"""
    creds_json = GOOGLE_CREDENTIALS_JSON
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS 환경변수가 없습니다.")
    creds_dict = json.loads(creds_json)
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client


def load_history() -> pd.DataFrame:
    """Google Sheets에서 리뷰 히스토리 로드"""
    try:
        client    = get_gspread_client()
        sheet     = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)
        records   = sheet.get_all_records()
        if not records:
            return pd.DataFrame(columns=["date", "asin", "title", "category", "price", "reviews", "link"])
        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        log.info(f"히스토리 로드 완료: {len(df)}건")
        return df
    except Exception as e:
        log.error(f"히스토리 로드 실패: {e}")
        return pd.DataFrame(columns=["date", "asin", "title", "category", "price", "reviews", "link"])


def save_history(new_rows: list):
    """
    오늘 수집한 데이터만 Google Sheets에 추가 (append).
    30일 이상 지난 행은 주기적으로 정리.
    """
    try:
        client    = get_gspread_client()
        sheet     = client.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)

        # 시트가 비어있으면 헤더 추가
        if sheet.row_count <= 1 and not sheet.get_all_values():
            sheet.append_row(["date", "asin", "title", "category", "price", "reviews", "link"])

        today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row in new_rows:
            sheet.append_row([
                today_str,
                row.get("asin", ""),
                row.get("title", ""),
                row.get("category", ""),
                row.get("price", ""),
                str(row.get("reviews", "0")),
                row.get("link", ""),
            ])

        log.info(f"Google Sheets 저장 완료: {len(new_rows)}건 추가")

        # 30일 초과 행 정리
        _cleanup_old_history(sheet)

    except Exception as e:
        log.error(f"Google Sheets 저장 실패: {e}")


def _cleanup_old_history(sheet):
    """30일 이상 지난 히스토리 행 삭제"""
    try:
        records  = sheet.get_all_records()
        cutoff   = datetime.now() - timedelta(days=30)
        to_delete = []
        for i, r in enumerate(records, start=2):  # 1행=헤더
            try:
                row_date = pd.to_datetime(r["date"])
                if row_date < cutoff:
                    to_delete.append(i)
            except:
                pass
        # 뒤에서부터 삭제 (인덱스 밀림 방지)
        for row_idx in reversed(to_delete):
            sheet.delete_rows(row_idx)
        if to_delete:
            log.info(f"오래된 히스토리 {len(to_delete)}건 정리 완료")
    except Exception as e:
        log.warning(f"히스토리 정리 중 오류: {e}")


def inject_test_history(today_products: list) -> pd.DataFrame:
    """
    [테스트 모드 전용]
    오늘 수집한 상품 기반으로 7일 전 가짜 데이터 생성.
    """
    log.info("[TEST MODE] 가짜 7일치 히스토리 데이터 생성 중...")
    fake_rows      = []
    seven_days_ago = datetime.now() - timedelta(days=7)

    for p in today_products:
        current_reviews = parse_review_count(p["reviews"])
        if random.random() > 0.5:
            past_reviews = max(0, current_reviews - random.randint(50, 150))
        else:
            past_reviews = current_reviews

        fake_rows.append({
            "date":     seven_days_ago,
            "asin":     p["asin"],
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
    """
    [개선 3] 리뷰 문자열 → 정수 변환
    "1,234個の評価", "1234件", "1,234" 등 다양한 형태 처리
    """
    try:
        # 숫자와 콤마만 남기고 제거 후 파싱
        numbers = re.findall(r'[\d,]+', str(review_str))
        if numbers:
            return int(numbers[0].replace(",", ""))
    except:
        pass
    return 0


def extract_asin(link: str) -> str:
    """상품 링크에서 ASIN 추출"""
    try:
        parts = link.split("/dp/")
        if len(parts) > 1:
            return parts[1].split("/")[0].split("?")[0]
    except:
        pass
    return link


def is_banned(title: str) -> bool:
    """금지 키워드 포함 여부 확인"""
    title_lower = title.lower()
    return any(b.lower() in title_lower for b in BANNED_KEYWORDS)


# ============================================================
# 번역 / 스마트스토어 제목 생성
# ============================================================

def translate_to_korean(text: str) -> str:
    """
    [개선 4] 번역 실패 시 None 반환 → 호출부에서 스킵 처리
    """
    try:
        result = GoogleTranslator(source="ja", target="ko").translate(text)
        # 번역 결과가 일본어 그대로인지 체크 (번역 실패 감지)
        if result and result.strip() and result != text:
            return result.strip()
        log.warning(f"번역 결과 이상 (원문 그대로): {text[:30]}")
        return None
    except Exception as e:
        log.warning(f"번역 실패: {e} | 원문: {text[:30]}")
        return None


SMARTSTORE_BANNED_PATTERNS = [
    "할인", "세일", "특가", "최저가", "무료배송", "증정", "사은품",
    "이벤트", "기간한정", "한정판매", "쿠폰", "적립",
    "대박", "강추", "인기폭발", "완판", "품절대란", "필수템",
]
SMARTSTORE_SPECIAL_CHARS = r'[♥★☆◆▶◀※↑↓→←【】『』《》♪♬!！?？@#$%^&*()]'


def create_smartstore_title(title_ja: str) -> str | None:
    """
    네이버 스마트스토어 상품명 규정에 맞는 제목 생성.
    번역 실패 시 None 반환.
    """
    translated = translate_to_korean(title_ja)
    if translated is None:
        return None  # [개선 4] 번역 실패 → 스킵

    cleaned = re.sub(SMARTSTORE_SPECIAL_CHARS, " ", translated)
    for pattern in SMARTSTORE_BANNED_PATTERNS:
        cleaned = cleaned.replace(pattern, "")
    cleaned     = re.sub(r"\s+", " ", cleaned).strip()
    smart_title = f"일본 정품 {cleaned}"

    if len(smart_title) > 50:
        smart_title = smart_title[:50].rsplit(" ", 1)[0]

    return smart_title


# ============================================================
# 네이버 쇼핑 API - 2단계 검색
# ============================================================

def naver_search(keyword: str) -> int:
    """네이버 쇼핑 검색 결과 수 반환. 실패 시 -1 반환."""
    url     = "https://openapi.naver.com/v1/search/shop.json"
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
        return -1


def extract_search_keywords(title_ja: str) -> tuple | None:
    """
    [개선 2] 브랜드명 + 핵심 상품명 추출 개선.
    - 앞의 괄호/특수문자 덩어리 제거 후 첫 단어를 브랜드로 추출
    - 번역 실패 시 None 반환
    """
    translated = translate_to_korean(title_ja)
    if translated is None:
        return None  # [개선 4] 번역 실패 → 스킵

    # 괄호로 묶인 앞부분 제거: 【お得セット】, (セット), ＜数量限定＞ 등
    cleaned = re.sub(r'^[\s\[【\(（＜《「『]+.*?[\]】\)）＞》」』]+\s*', '', translated)
    cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
    words   = [w for w in cleaned.split() if len(w) > 1]

    if not words:
        return None

    brand_keyword = words[0]                                    # 브랜드 (첫 단어)
    core_keyword  = " ".join(words[1:4]) if len(words) > 1 else words[0]  # 핵심 상품명 (2~4번째)

    return brand_keyword, core_keyword


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
        soup  = BeautifulSoup(res.text, "html.parser")
        items = soup.select(".zg-grid-general-faceout")

        if not items:
            log.warning(f"[{category}] 상품 항목 없음. 셀렉터 확인 필요.")
            return []

        log.info(f"[{category}] {len(items)}개 항목 발견")

        for rank, item in enumerate(items[:30], start=1):
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
            reviews = review_el.text.strip() if review_el else "0"
            link    = ("https://amazon.co.jp" + link_el.get("href")) if link_el else ""
            asin    = extract_asin(link)

            products.append({
                "category": category,
                "rank":     rank,
                "title":    title,
                "price":    price,
                "reviews":  reviews,   # 원본 문자열 그대로 저장 (파싱은 나중에)
                "link":     link,
                "asin":     asin,
            })

    except Exception as e:
        log.error(f"[{category}] 크롤링 오류: {e}")

    return products


def crawl_all() -> list:
    """
    [개선 5] 전체 카테고리 크롤링 + ASIN 기준 중복 제거
    """
    all_products = []
    seen_asins   = set()

    for category, url in CATEGORIES.items():
        log.info(f"크롤링 시작: {category}")
        products = crawl_category(category, url)

        for p in products:
            if p["asin"] and p["asin"] in seen_asins:
                log.info(f"중복 ASIN 스킵: {p['asin']} ({p['title'][:20]})")
                continue
            seen_asins.add(p["asin"])
            all_products.append(p)

        log.info(f"[{category}] {len(products)}개 수집")

    log.info(f"전체 수집 완료: {len(all_products)}개 (중복 제거 후)")
    return all_products


# ============================================================
# 리뷰 급증 감지
# ============================================================

def detect_review_spikes(today_products: list, history_df: pd.DataFrame) -> list:
    """7일 전 리뷰수와 비교하여 급증 상품 필터링"""
    if history_df.empty:
        log.warning("히스토리 데이터 없음.")
        return []

    seven_days_ago = datetime.now() - timedelta(days=7)
    old_df = history_df[
        (history_df["date"] >= seven_days_ago - timedelta(days=1)) &
        (history_df["date"] <= seven_days_ago + timedelta(days=1))
    ]

    if old_df.empty:
        log.warning("7일 전 데이터 없음. 데이터 누적 중...")
        return []

    old_reviews = dict(zip(old_df["asin"], old_df["reviews"].apply(parse_review_count)))

    spiked = []
    for p in today_products:
        asin          = p["asin"]
        current_count = parse_review_count(p["reviews"])
        past_count    = old_reviews.get(asin)

        if past_count is None:
            continue

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
    """
    네이버 쇼핑 2단계 검색으로 진짜 블루오션만 필터링.
    번역 실패 상품은 스킵.
    """
    unlisted = []
    for p in products:

        # [개선 4] 번역 실패 시 스킵
        korean_title = create_smartstore_title(p["title"])
        if korean_title is None:
            log.warning(f"번역 실패로 스킵: {p['title'][:30]}")
            continue
        p["korean_title"] = korean_title

        # [개선 2] 키워드 추출 실패 시 스킵
        kw_result = extract_search_keywords(p["title"])
        if kw_result is None:
            log.warning(f"키워드 추출 실패로 스킵: {p['title'][:30]}")
            continue
        brand_kw, core_kw = kw_result

        # 1차: 브랜드명 검색
        brand_count = naver_search(brand_kw)
        time.sleep(0.5)
        if brand_count == -1:
            log.warning(f"네이버 API 오류(1차), 스킵: {brand_kw}")
            continue
        if brand_count > NAVER_MAX_COUNT:
            log.info(f"1차 등록됨({brand_count}건) [{brand_kw}], 스킵")
            continue

        # 2차: 핵심 상품명 검색
        core_count = naver_search(core_kw)
        time.sleep(0.5)
        if core_count == -1:
            log.warning(f"네이버 API 오류(2차), 스킵: {core_kw}")
            continue
        if core_count > NAVER_MAX_COUNT:
            log.info(f"2차 등록됨({core_count}건) [{core_kw}], 스킵")
            continue

        # 둘 다 0건 → 진짜 블루오션
        p["naver_brand_count"] = brand_count
        p["naver_core_count"]  = core_count
        p["naver_search_1"]    = brand_kw
        p["naver_search_2"]    = core_kw
        unlisted.append(p)
        log.info(f"✅ 블루오션: {korean_title[:30]} | 브랜드({brand_kw}):{brand_count}건 / 상품명({core_kw}):{core_count}건")

    log.info(f"네이버 미등록 상품: {len(unlisted)}개")
    return unlisted


# ============================================================
# 이메일 발송
# ============================================================

def build_email_body(products: list, is_test: bool) -> str:
    today      = datetime.now().strftime("%Y-%m-%d")
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
              <div style="background:#f5f5f5;border-left:3px solid #ff9900;padding:8px 12px;margin:6px 0;border-radius:0 4px 4px 0;">
                <span style="font-size:11px;color:#999;">📋 스마트스토어 상품명 (복붙용)</span><br>
                <span style="font-size:14px;font-weight:bold;color:#0f1111;user-select:all;">{p['korean_title']}</span>
              </div>
              <p style="color:#666;font-size:13px;margin:4px 0;">원제: {p['title']}</p>
              <div style="display:flex;gap:16px;margin:8px 0;flex-wrap:wrap;">
                <span>💴 <strong>{p['price']}</strong></span>
                <span>📝 리뷰 {past}→{current} (<span style="color:green;font-weight:bold;">+{increase}개/7일</span>)</span>
                <span>🔍 브랜드({p.get('naver_search_1','')}):{p.get('naver_brand_count',0)}건 / 상품명({p.get('naver_search_2','')}):{p.get('naver_core_count',0)}건</span>
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
    today   = datetime.now().strftime("%Y-%m-%d")
    subject = f"[{'TEST' if is_test else '실전'}] Amazon 자동소싱 {today} - {len(products)}개 발굴"
    body    = build_email_body(products, is_test)

    msg = MIMEMultipart()
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = EMAIL_ADDRESS
    msg["To"]      = TO_ADDRESS
    msg.attach(MIMEText(body, "html", "utf-8"))

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
    today = datetime.now().strftime("%Y-%m-%d")
    log.info(f"========== 소싱 시작 ({today}) | 모드: {'TEST' if TEST_MODE else '실전'} ==========")

    # 1. Amazon JP 크롤링 (ASIN 중복 제거 포함)
    today_products = crawl_all()
    if not today_products:
        log.error("수집된 상품 없음. 종료.")
        return

    # 2. 히스토리 로드 (Google Sheets)
    history_df = load_history()

    # 3. 테스트 모드: 가짜 7일치 데이터 주입
    if TEST_MODE:
        fake_history = inject_test_history(today_products)
        history_df   = pd.concat([history_df, fake_history], ignore_index=True)

    # 4. 오늘 데이터 Google Sheets에 저장
    if not TEST_MODE:
        save_history(today_products)

    # 5. 리뷰 급증 감지
    spiked_products = detect_review_spikes(today_products, history_df)
    if not spiked_products:
        log.info("리뷰 급증 상품 없음. 이메일 미발송.")
        return

    # 6. 네이버 미등록 필터 (번역 실패 스킵 포함)
    final_products = filter_naver_unlisted(spiked_products)

    # 7. CSV 저장
    csv_name = f"amazon_sourcing_{today}{'_test' if TEST_MODE else ''}.csv"
    pd.DataFrame(final_products).to_csv(csv_name, index=False, encoding="utf-8-sig")
    log.info(f"CSV 저장: {csv_name} ({len(final_products)}건)")

    # 8. 이메일 발송
    send_email(final_products, csv_name, is_test=TEST_MODE)

    log.info("========== 소싱 완료 ==========")


if __name__ == "__main__":
    main()
