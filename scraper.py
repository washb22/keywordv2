# scraper.py - 네이버 키워드 순위 체크 (기존 localkeyword-backend에서 이관)

import time
import random
import urllib.parse
import re
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- 보조 함수들 ---
CAFE_HOSTS = {"cafe.naver.com", "m.cafe.naver.com"}


def extract_cafe_ids(url: str):
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return set()
    ids = set()
    qs = urllib.parse.parse_qs(p.query)
    for key in ("articleid", "clubid", "articleId", "clubId"):
        for val in qs.get(key, []):
            if val.isdigit():
                ids.add(val)
    for token in re.split(r"[/?=&]", p.path):
        if token.isdigit() and len(token) >= 4:
            ids.add(token)
    return ids


def url_matches(target_url: str, candidate_url: str) -> bool:
    try:
        t, c = urllib.parse.urlparse(target_url), urllib.parse.urlparse(candidate_url)
    except Exception:
        return False
    t_host, c_host = t.netloc.split(":")[0].lower(), c.netloc.split(":")[0].lower()
    if (t_host in CAFE_HOSTS) or (c_host in CAFE_HOSTS):
        t_ids, c_ids = extract_cafe_ids(target_url), extract_cafe_ids(candidate_url)
        if t_ids and c_ids and (t_ids & c_ids):
            return True
        if t_ids and any(_id in candidate_url for _id in t_ids):
            return True
    return candidate_url.startswith(target_url[: min(len(target_url), 60)])


def url_or_title_matches(target_url, target_title, href, link_text):
    if url_matches(target_url, href):
        return True
    if target_title and link_text:
        normalized_target = "".join(target_title.split()).lower()
        normalized_link = "".join(link_text.split()).lower()
        if len(normalized_target) > 3 and len(normalized_link) > 3:
            if normalized_target in normalized_link or normalized_link in normalized_target:
                return True
    return False


def human_sleep(a=0.8, b=1.8):
    time.sleep(random.uniform(a, b))


def is_content_url(href):
    if not href:
        return False
    exclude_patterns = [
        'javascript:', '#', '/search.naver', 'tab=', 'mode=', 'option=',
        'query=', 'where=', 'sm=', 'ssc=', '/my.naver', 'help.naver',
        'shopping.naver', 'terms.naver.com', 'nid.naver.com', 'ader.naver.com',
        'mkt.naver.com', 'section.blog.naver.com', 'section.cafe.naver.com',
        'MyBlog.naver'
    ]
    if any(p in href for p in exclude_patterns):
        return False
    if 'blog.naver.com' in href:
        return bool(re.search(r'blog\.naver\.com/[^/]+/\d+', href))
    if 'cafe.naver.com' in href:
        return bool(re.search(r'(articleid|clubid|\d{6,})', href, re.I))
    if 'in.naver.com' in href and '/contents/' in href:
        return True
    if any(p in href for p in ['post.naver.com', 'kin.naver.com', 'tv.naver.com', 'news.naver.com']):
        return True
    return False


def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,2200")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=options)


def extract_section_title(section):
    try:
        for sel in ["h2", "h3", ".fds-comps-header-headline", "[class*='headline']"]:
            els = section.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                text = el.text.strip()
                if text and len(text) > 1 and len(text) < 50:
                    text = text.split("\n")[0].strip()
                    if "더보기" in text:
                        text = text.split("더보기")[0].strip()
                    if text:
                        return text
        section_text = section.text[:300] if section.text else ""
        if "인기글" in section_text:
            match = re.search(r'([\w·\s]+)?인기글', section_text)
            if match:
                title = match.group(0).strip()
                if len(title) < 30:
                    return title
            return "인기글"
        class_name = section.get_attribute("class") or ""
        if "ad_section" in class_name or "ad" in class_name.split():
            return "광고"
        if "sp_nblog" in class_name:
            return "블로그"
        if "sp_ncafe" in class_name:
            return "카페"
        if "ntalk_wrap" in class_name:
            return "오픈톡"
    except Exception:
        pass
    return "검색결과"


def extract_post_links(section):
    """섹션에서 메인 게시글 제목 링크만 추출 (댓글/답변/관련글 제외)

    카드 구조: [15px 카페/블로그 이름] → [13px 제목] → [13px 본문/댓글/관련글]
    각 카드에서 첫 번째 콘텐츠 링크만 순위로 인정.
    """
    results = []
    seen_hrefs = set()

    try:
        all_links = section.find_elements(By.CSS_SELECTOR,
            "a[href*='blog.naver.com'], "
            "a[href*='cafe.naver.com'], "
            "a[href*='in.naver.com/'], "
            "a[href*='post.naver.com'], "
            "a[href*='kin.naver.com']"
        )

        card_found_content = False  # 현재 카드에서 이미 제목을 찾았는지

        for link in all_links:
            try:
                if not link.is_displayed():
                    continue
                href = link.get_attribute("href") or ""
                text = link.text.strip()
                if not text or len(text) < 3:
                    continue

                # 15px 링크 = 카페/블로그 이름 (새 카드 시작)
                font_size = link.value_of_css_property("font-size")
                size_px = float(font_size.replace("px", "")) if font_size else 13

                if size_px >= 15:
                    # 새 카드 시작 - 다음 콘텐츠 링크가 이 카드의 제목
                    card_found_content = False
                    continue

                # 이미 이 카드의 제목을 찾았으면 나머지(본문/댓글/관련글) 무시
                if card_found_content:
                    continue

                # 콘텐츠 URL인지 체크
                if not is_content_url(href):
                    continue

                # 같은 href 중복 방지
                if href in seen_hrefs:
                    continue

                if len(text) > 5:
                    seen_hrefs.add(href)
                    results.append((href, text))
                    card_found_content = True  # 이 카드의 제목 찾음, 나머지 스킵

            except Exception:
                continue
    except Exception as e:
        print(f"링크 추출 오류: {e}")
    return results


def get_divider_y(driver):
    for selector in ['.spw_fsolid._fsolid_body', '.spw_fsolid._fsolid_head']:
        try:
            y = driver.execute_script(f'''
                var el = document.querySelector('{selector}');
                if(el) return el.getBoundingClientRect().top + window.scrollY;
                return -1;
            ''')
            if y > 0:
                return y
        except Exception:
            continue
    return None


def check_sections(driver, keyword, post_url, post_title):
    sections = driver.find_elements(By.CSS_SELECTOR, "#main_pack .sc_new")
    print(f"[{keyword}] {len(sections)}개 섹션 발견")

    skip_titles = ["광고", "AI 브리핑", "브랜드", "가격비교", "쇼핑", "스토어"]
    rank = 0

    for section in sections:
        try:
            if not section.is_displayed() or section.size['height'] < 50:
                continue
            section_class = section.get_attribute("class") or ""
            if "ad_section" in section_class:
                continue
            section_title = extract_section_title(section)
            if any(sk in section_title for sk in skip_titles):
                continue

            post_links = extract_post_links(section)
            for link_idx, (href, text) in enumerate(post_links):
                rank += 1
                if url_or_title_matches(post_url, post_title, href, text):
                    print(f"[{keyword}] 통합 {rank}위에서 발견! (섹션 '{section_title}' {link_idx+1}번째 글)")
                    return ("노출", rank, section_title)
            if not post_links:
                rank += 1
        except Exception:
            continue
    return None


def run_check(keyword: str, post_url: str, post_title: str = None) -> tuple:
    """키워드 순위 확인 메인 함수"""
    print(f"--- '{keyword}' 순위 확인 시작 ---")
    driver = None
    try:
        driver = create_driver()
        q = urllib.parse.quote(keyword)
        print(f"[{keyword}] 통합검색 페이지 접근 중...")
        driver.get(f"https://search.naver.com/search.naver?query={q}")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "main_pack")))
        human_sleep()
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        result = check_sections(driver, keyword, post_url, post_title)
        if result:
            return result
        print(f"[{keyword}] 통합검색 1페이지에서 URL을 찾지 못함")
        return ("노출X", 999, None)
    except Exception as e:
        print(f"[{keyword}] 순위 확인 중 오류 발생: {str(e)}")
        traceback.print_exc()
        return ("확인 실패", 999, None)
    finally:
        if driver:
            driver.quit()
        print(f"--- '{keyword}' 순위 확인 완료 ---\n")
