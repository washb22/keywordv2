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
        for link in all_links:
            try:
                if not link.is_displayed():
                    continue
                href = link.get_attribute("href") or ""
                text = link.text.strip()
                if not is_content_url(href):
                    continue
                if href in seen_hrefs:
                    continue
                if len(text) > 5:
                    seen_hrefs.add(href)
                    results.append((href, text))
            except Exception:
                continue
    except Exception as e:
        print(f"링크 추출 오류: {e}")
    return results


def _filter_card_titles(section):
    """인기글 묶음 섹션에서 카드별 메인 제목만 추출 (댓글/답변/관련글 제외)

    카드 구분: 15px 폰트 = 카페/블로그 이름 = 새 카드 시작
    각 카드에서 첫 번째 콘텐츠 링크만 게시글 제목으로 인정
    """
    results = []
    seen_hrefs = set()
    card_found = False

    try:
        all_links = section.find_elements(By.CSS_SELECTOR,
            "a[href*='blog.naver.com'], "
            "a[href*='cafe.naver.com'], "
            "a[href*='in.naver.com/'], "
            "a[href*='post.naver.com'], "
            "a[href*='kin.naver.com']"
        )
        for link in all_links:
            try:
                if not link.is_displayed():
                    continue
                href = link.get_attribute("href") or ""
                text = link.text.strip()
                if not text or len(text) < 3:
                    continue

                font_size = link.value_of_css_property("font-size")
                size_px = float(font_size.replace("px", "")) if font_size else 13

                if size_px >= 15:
                    card_found = False
                    continue

                if card_found:
                    continue

                if not is_content_url(href):
                    continue
                if href in seen_hrefs:
                    continue
                if len(text) > 5:
                    seen_hrefs.add(href)
                    results.append((href, text))
                    card_found = True
            except Exception:
                continue
    except Exception:
        pass
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


def _collect_cafe_names_from_section(section, is_grouped, max_count=3):
    """섹션에서 카페 이름 N개 추출. 인기글이면 카드 제목(15px+), 아니면 모든 카페 링크"""
    cafe_names = []
    seen = set()
    try:
        links = section.find_elements(By.CSS_SELECTOR, "a[href*='cafe.naver.com']")
        for link in links:
            try:
                if not link.is_displayed():
                    continue
                if is_grouped:
                    fs = link.value_of_css_property("font-size")
                    size_px = float(fs.replace("px", "")) if fs else 13
                    if size_px < 15:
                        continue
                name = _extract_cafe_name_from_link(link)
                if not name:
                    continue
                if not is_grouped and len(name) > 20:
                    continue
                if name in seen:
                    continue
                seen.add(name)
                cafe_names.append(name)
                if len(cafe_names) >= max_count:
                    break
            except Exception:
                continue
    except Exception:
        pass
    return cafe_names


def check_sections(driver, keyword, post_url, post_title):
    """순위 체크 + 상위 카페 3개 추출을 한 번에 수행.
    Returns: (rank_result_or_None, cafe_list)
    """
    sections = driver.find_elements(By.CSS_SELECTOR, "#main_pack .sc_new")
    print(f"[{keyword}] {len(sections)}개 섹션 발견", flush=True)

    divider_y = get_divider_y(driver)
    print(f"[{keyword}] 윗탭/아랫탭 경계 Y: {divider_y}", flush=True)

    skip_titles = ["광고", "AI 브리핑", "브랜드", "가격비교", "쇼핑", "스토어"]
    upper_rank = 0
    lower_rank = 0

    rank_result = None
    top_cafes = []

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
            section_y = section.location['y']
            is_upper = divider_y is None or section_y < divider_y
            is_grouped = "인기글" in section_title

            # 상위 카페 3개 추출: 윗탭 + 카페탭 아닌 것 + 아직 못 찾은 경우
            if is_upper and not top_cafes and "sp_ncafe" not in section_class:
                cafes = _collect_cafe_names_from_section(section, is_grouped, 3)
                if cafes:
                    top_cafes = cafes
                    print(f"[{keyword}] 상위 카페: {top_cafes}", flush=True)

            # 순위 체크 (이미 찾았으면 스킵하고 카페만 계속 탐색)
            if rank_result is None:
                if is_upper:
                    upper_rank += 1
                else:
                    lower_rank += 1

                post_links = _filter_card_titles(section) if is_grouped else extract_post_links(section)

                for link_idx, (href, text) in enumerate(post_links):
                    if url_or_title_matches(post_url, post_title, href, text):
                        tab = "윗탭" if is_upper else "아랫탭"
                        tab_rank = upper_rank if is_upper else lower_rank
                        if is_grouped:
                            in_rank = link_idx + 1
                            print(f"[{keyword}] '{section_title}' {in_rank}위에서 발견!", flush=True)
                            rank_result = (section_title, in_rank, section_title)
                        else:
                            print(f"[{keyword}] {tab} {tab_rank}위에서 발견!", flush=True)
                            rank_result = (tab, tab_rank, tab)
                        break

            # 둘 다 찾았으면 종료
            if rank_result and top_cafes:
                break
        except Exception:
            continue
    return rank_result, top_cafes


def _extract_cafe_name_from_link(link):
    """카페 링크에서 카페 표시명 추출"""
    try:
        # 카페 이름은 보통 링크 내부 또는 부모 요소의 특정 클래스에 있음
        # 1) aria-label 또는 title 속성
        for attr in ("aria-label", "title"):
            v = (link.get_attribute(attr) or "").strip()
            if v and 1 < len(v) < 30 and "더보기" not in v:
                return v
        # 2) 링크 텍스트
        txt = (link.text or "").strip()
        if txt and 1 < len(txt) < 30:
            return txt
    except Exception:
        pass
    return None


def get_top_cafes(driver, keyword: str, max_count: int = 3):
    """윗탭 최상단 카페 관련 섹션에서 카페 이름 N개 추출.
    인기글 묶음이면 거기서, 아니면 개별 카페 섹션에서.
    주의: 카페 섹션(카페 탭 결과) 은 제외.
    """
    try:
        q = urllib.parse.quote(keyword)
        driver.get(f"https://search.naver.com/search.naver?query={q}")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "main_pack")))
        human_sleep()
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.2)

        sections = driver.find_elements(By.CSS_SELECTOR, "#main_pack .sc_new")
        divider_y = get_divider_y(driver)
        skip_titles = ["광고", "AI 브리핑", "브랜드", "가격비교", "쇼핑", "스토어", "카페"]

        for section in sections:
            try:
                if not section.is_displayed() or section.size['height'] < 50:
                    continue
                section_class = section.get_attribute("class") or ""
                if "ad_section" in section_class:
                    continue
                # 카페 섹션(카페 탭 결과) 자체는 제외
                if "sp_ncafe" in section_class:
                    continue
                section_title = extract_section_title(section)
                if any(sk in section_title for sk in skip_titles):
                    continue
                section_y = section.location['y']
                is_upper = divider_y is None or section_y < divider_y
                if not is_upper:
                    continue

                is_grouped = "인기글" in section_title

                # 인기글 묶음: 각 카드의 카페명(15px 이상 폰트) 추출
                if is_grouped:
                    cafe_names = []
                    seen = set()
                    links = section.find_elements(By.CSS_SELECTOR, "a[href*='cafe.naver.com']")
                    for link in links:
                        try:
                            if not link.is_displayed():
                                continue
                            fs = link.value_of_css_property("font-size")
                            size_px = float(fs.replace("px", "")) if fs else 13
                            if size_px < 15:
                                continue
                            name = _extract_cafe_name_from_link(link)
                            if not name:
                                continue
                            if name in seen:
                                continue
                            seen.add(name)
                            cafe_names.append(name)
                            if len(cafe_names) >= max_count:
                                break
                        except Exception:
                            continue
                    if cafe_names:
                        print(f"[카페추출] '{keyword}' 인기글 섹션: {cafe_names}")
                        return cafe_names[:max_count]

                # 그 외 (통합검색 개별 카페 글이 섞인 섹션): 카페 링크 중 카페명 추출
                else:
                    cafe_names = []
                    seen = set()
                    links = section.find_elements(By.CSS_SELECTOR, "a[href*='cafe.naver.com']")
                    for link in links:
                        try:
                            if not link.is_displayed():
                                continue
                            name = _extract_cafe_name_from_link(link)
                            if not name:
                                continue
                            # 너무 긴 텍스트는 게시글 제목일 가능성 → 제외
                            if len(name) > 20:
                                continue
                            if name in seen:
                                continue
                            seen.add(name)
                            cafe_names.append(name)
                            if len(cafe_names) >= max_count:
                                break
                        except Exception:
                            continue
                    if cafe_names:
                        print(f"[카페추출] '{keyword}' {section_title}: {cafe_names}")
                        return cafe_names[:max_count]
            except Exception:
                continue
    except Exception as e:
        print(f"[카페추출] '{keyword}' 오류: {e}")
    return []


def run_check(keyword: str, post_url: str, post_title: str = None, driver=None) -> tuple:
    """키워드 순위 확인 + 상위 카페 추출 (한 번의 페이지 방문).
    driver가 주어지면 재사용 (종료 안 함), 없으면 새로 생성 후 종료.
    Returns: (status, rank, section, top_cafes)
    """
    print(f"--- '{keyword}' 순위 확인 시작 ---", flush=True)
    own_driver = False
    try:
        if driver is None:
            driver = create_driver()
            own_driver = True
        q = urllib.parse.quote(keyword)
        print(f"[{keyword}] 통합검색 페이지 접근 중...", flush=True)
        driver.get(f"https://search.naver.com/search.naver?query={q}")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "main_pack")))
        human_sleep(0.4, 0.9)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.8)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.6)
        rank_result, top_cafes = check_sections(driver, keyword, post_url, post_title)
        if rank_result:
            return (*rank_result, top_cafes)
        print(f"[{keyword}] 통합검색 1페이지에서 URL을 찾지 못함", flush=True)
        return ("노출X", 999, None, top_cafes)
    except Exception as e:
        print(f"[{keyword}] 순위 확인 중 오류 발생: {str(e)}", flush=True)
        traceback.print_exc()
        return ("확인 실패", 999, None, [])
    finally:
        if own_driver and driver:
            driver.quit()
        print(f"--- '{keyword}' 순위 확인 완료 ---\n", flush=True)
