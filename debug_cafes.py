"""
카페명 추출 디버그 스크립트
사용법: python debug_cafes.py 마그밀
"""
import sys
import time
import urllib.parse
from dotenv import load_dotenv

# Windows 콘솔 UTF-8
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

load_dotenv()

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from scraper import (
    create_driver, get_divider_y, extract_section_title,
    _is_cafe_home_url, _collect_cafe_names_from_section,
)


def debug_keyword(keyword):
    print(f"\n{'='*60}")
    print(f"디버그: '{keyword}' 카페명 추출")
    print('='*60)

    driver = create_driver()
    try:
        q = urllib.parse.quote(keyword)
        driver.get(f"https://search.naver.com/search.naver?query={q}")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "main_pack")))
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)

        sections = driver.find_elements(By.CSS_SELECTOR, "#main_pack .sc_new")
        divider_y = get_divider_y(driver)
        print(f"\n총 {len(sections)}개 섹션, 윗탭 경계 Y={divider_y}\n")

        skip_titles = ["광고", "AI 브리핑", "브랜드", "가격비교", "쇼핑", "스토어"]
        all_cafes = []

        for idx, section in enumerate(sections):
            try:
                if not section.is_displayed() or section.size['height'] < 50:
                    continue
                section_class = section.get_attribute("class") or ""
                if "ad_section" in section_class:
                    continue
                title = extract_section_title(section)
                if any(sk in title for sk in skip_titles):
                    continue
                y = section.location['y']
                is_upper = divider_y is None or y < divider_y
                if not is_upper:
                    continue
                if "sp_ncafe" in section_class:
                    continue

                print(f"\n--- 섹션 {idx}: '{title}' (y={y:.0f}, class={section_class[:60]}) ---")

                # 모든 cafe 링크 덤프
                links = section.find_elements(By.CSS_SELECTOR, "a[href*='cafe.naver.com']")
                print(f"  cafe 링크 {len(links)}개:")
                for i, link in enumerate(links[:15]):
                    try:
                        href = link.get_attribute("href") or ""
                        text = (link.text or "").strip().replace('\n', ' | ')[:60]
                        is_home = _is_cafe_home_url(href)
                        marker = "🏠" if is_home else "📄"
                        print(f"    [{i}] {marker} text='{text}'")
                        print(f"         href={href[:100]}")
                    except Exception as e:
                        print(f"    [{i}] 오류: {e}")

                # 우리 추출 함수 돌려보기
                extracted = _collect_cafe_names_from_section(section, "인기글" in title, 3)
                print(f"  → 추출 결과: {extracted}")
                all_cafes.extend(extracted)

                if len(all_cafes) >= 3:
                    break
            except Exception as e:
                print(f"섹션 {idx} 오류: {e}")

        print(f"\n{'='*60}")
        print(f"최종 추출된 카페 (중복 제거): {list(dict.fromkeys(all_cafes))[:3]}")
        print('='*60)

    finally:
        driver.quit()


if __name__ == '__main__':
    kw = sys.argv[1] if len(sys.argv) > 1 else "마그밀"
    debug_keyword(kw)
