# main.py - KeywordV2 메인 스크립트
# 사용법:
#   python main.py              → 즉시 순위 체크
#   python main.py --watch      → 스프레드시트 버튼 감지 모드 (5분 간격 폴링)
#   python main.py --setup      → 스프레드시트 초기 세팅

import os
import sys
import time
import argparse
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def now_kst():
    return datetime.now(KST)
from dotenv import load_dotenv

# .env 로드
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from sheet import read_keywords, write_results, check_request_flag, setup_sheet, write_status_section
from scraper import run_check
from telegram_notify import send_report
from naver_ad_api import get_search_volume
import random


def build_and_write_status(results, all_keywords, cafe_map):
    """작업현황 표 (J~P열) 생성 및 기록. 카페는 run_check 단계에서 수집됨."""
    print("\n[작업현황] 집계 시작...")

    # 키워드 단위 고유 목록
    unique_keywords = []
    seen = set()
    for kw in all_keywords:
        k = kw['keyword']
        if k and k not in seen:
            seen.add(k)
            unique_keywords.append(k)

    # 키워드별 검색량 (광고 API)
    volume_map = {}
    for k in unique_keywords:
        volume_map[k] = get_search_volume(k)

    status_rows = []
    for r in results:
        keyword = r['keyword']
        current_rank = r.get('status', '')  # "윗탭 3위" / "미노출" 등
        if current_rank == '미노출' or not current_rank:
            state_label = '❌ 누락'
            rank_display = ''
        elif '아랫탭' in current_rank or '인기글' in current_rank:
            state_label = '⚠️ 하위탭'
            rank_display = current_rank
        else:
            state_label = '✅ 잡힘'
            rank_display = current_rank

        status_rows.append({
            'keyword': keyword,
            'volume': volume_map.get(keyword, 0),
            'cafes': cafe_map.get(keyword, []),
            'current_rank': rank_display,
            'status': state_label,
        })

    write_status_section(status_rows)


def check_all_keywords():
    """전체 키워드 순위 체크 + 스프레드시트 기록 + 텔레그램 알림"""
    print(f"\n{'='*50}")
    print(f"순위 체크 시작: {now_kst().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    keywords = read_keywords()
    if not keywords:
        print("체크할 키워드가 없습니다.")
        return

    results = []
    cafe_map = {}
    for i, kw in enumerate(keywords, 1):
        print(f"[{i}/{len(keywords)}] '{kw['keyword']}' 체크 중...")

        try:
            status, rank, section, top_cafes = run_check(kw['keyword'], kw['url'], kw['title'])
        except Exception as e:
            print(f"  오류: {e}")
            status, rank, section, top_cafes = '확인 실패', 999, None, []

        if kw['keyword'] not in cafe_map or not cafe_map[kw['keyword']]:
            cafe_map[kw['keyword']] = top_cafes

        # 현재 상태 텍스트
        if status == '노출X':
            status_display = '미노출'
        elif rank and rank < 999:
            status_display = f'{section} {rank}위'
        else:
            status_display = status

        # 변동 계산 (이전 순위는 스프레드시트에서 읽어온 현재값이 이전값이 됨)
        # 첫 체크 시에는 변동 없음
        result = {
            'row': kw['row'],
            'keyword': kw['keyword'],
            'priority': kw.get('priority', '중'),
            'status': status_display,
            'rank': rank if rank and rank < 999 else '',
            'raw_status': status,
            'section': section,
            'prev_rank_display': '',
            'change': '',
            'checked_at': now_kst().strftime('%Y-%m-%d %H:%M')
        }
        results.append(result)

        # 네이버 차단 방지
        if i < len(keywords):
            delay = random.uniform(2, 4)
            print(f"  → {status_display} (다음 체크까지 {delay:.1f}초 대기)")
            time.sleep(delay)
        else:
            print(f"  → {status_display}")

    # 이전값 처리: 스프레드시트에서 현재 F열(현재순위) 값을 E열(이전순위)로 이동
    _fill_previous_values(results)

    # 스프레드시트에 결과 기록
    write_results(results)

    # 작업현황 표 (J~P열) 기록
    try:
        build_and_write_status(results, keywords, cafe_map)
    except Exception as e:
        print(f"[작업현황] 실패: {e}")

    # 텔레그램 알림
    send_report(results)

    print(f"\n{'='*50}")
    print(f"순위 체크 완료: {now_kst().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"총 {len(results)}개 키워드 처리")
    print(f"{'='*50}\n")


def check_selected_keywords(start_row, end_row):
    """선택한 행의 키워드만 순위 체크"""
    print(f"\n{'='*50}")
    print(f"선택 키워드 체크: {start_row}~{end_row}행")
    print(f"{'='*50}\n")

    all_keywords = read_keywords()
    # 해당 행 번호에 맞는 키워드만 필터
    keywords = [kw for kw in all_keywords if start_row <= kw['row'] <= end_row]

    if not keywords:
        print("해당 행에 키워드가 없습니다.")
        return

    results = []
    cafe_map = {}
    for i, kw in enumerate(keywords, 1):
        print(f"[{i}/{len(keywords)}] '{kw['keyword']}' 체크 중...")

        try:
            status, rank, section, top_cafes = run_check(kw['keyword'], kw['url'], kw['title'])
        except Exception as e:
            print(f"  오류: {e}")
            status, rank, section, top_cafes = '확인 실패', 999, None, []

        if kw['keyword'] not in cafe_map or not cafe_map[kw['keyword']]:
            cafe_map[kw['keyword']] = top_cafes

        if status == '노출X':
            status_display = '미노출'
        elif rank and rank < 999:
            status_display = f'{section} {rank}위'
        else:
            status_display = status

        result = {
            'row': kw['row'],
            'keyword': kw['keyword'],
            'priority': kw.get('priority', '중'),
            'status': status_display,
            'rank': rank if rank and rank < 999 else '',
            'raw_status': status,
            'section': section,
            'prev_rank_display': '',
            'change': '',
            'checked_at': now_kst().strftime('%Y-%m-%d %H:%M')
        }
        results.append(result)

        if i < len(keywords):
            delay = random.uniform(2, 4)
            print(f"  → {status_display} (다음 체크까지 {delay:.1f}초 대기)")
            time.sleep(delay)
        else:
            print(f"  → {status_display}")

    _fill_previous_values(results)
    write_results(results)

    # 작업현황 표 (J~P열) — 선택 체크한 키워드만 반영
    try:
        build_and_write_status(results, keywords, cafe_map)
    except Exception as e:
        print(f"[작업현황] 실패: {e}")

    print(f"\n선택 키워드 {len(results)}개 체크 완료!")


def _fill_previous_values(results):
    """스프레드시트의 F열(현재순위)을 E열(이전순위)로 이동 + 변동 계산"""
    from sheet import get_spreadsheet
    import re
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return

    try:
        worksheet = spreadsheet.worksheet('키워드')
        all_values = worksheet.get_all_values()

        for r in results:
            row_idx = r['row'] - 1  # 0-based index
            if row_idx < len(all_values):
                row_data = all_values[row_idx]
                # E열(인덱스4) = 현재 순위 ("윗탭 2위") → 이전 순위로 이동
                prev_display = row_data[4] if len(row_data) > 4 else ''
                r['prev_rank_display'] = prev_display

                # 변동 계산: "윗탭 2위" 에서 숫자 추출
                try:
                    prev_match = re.search(r'(\d+)위', prev_display)
                    prev_r = int(prev_match.group(1)) if prev_match else None
                    curr_r = r['rank'] if isinstance(r['rank'], int) else None
                    if prev_r and curr_r:
                        diff = prev_r - curr_r
                        if diff > 0:
                            r['change'] = f'▲{diff}'
                        elif diff < 0:
                            r['change'] = f'▼{abs(diff)}'
                        else:
                            r['change'] = '-'
                except (ValueError, TypeError):
                    pass
    except Exception as e:
        print(f"[이전값] 읽기 실패 (무시): {e}")


def watch_mode():
    """스프레드시트 버튼 감지 모드 - 5분마다 K1 셀 확인"""
    print("=" * 50)
    print("KeywordV2 감지 모드 시작")
    print("스프레드시트에서 '전체 순위 확인' 버튼을 누르면 자동 체크됩니다.")
    print("종료: Ctrl+C")
    print("=" * 50)

    while True:
        try:
            flag = check_request_flag()
            if flag == 'all':
                print(f"\n[감지] 전체 체크 요청! ({now_kst().strftime('%H:%M:%S')})")
                check_all_keywords()
            elif isinstance(flag, tuple):
                start_row, end_row = flag
                print(f"\n[감지] 선택 체크 요청 ({start_row}~{end_row}행) ({now_kst().strftime('%H:%M:%S')})")
                check_selected_keywords(start_row, end_row)
            else:
                print(f"[대기중] {now_kst().strftime('%H:%M:%S')} - 요청 없음", end='\r')

            time.sleep(300)  # 5분 간격
        except KeyboardInterrupt:
            print("\n감지 모드 종료")
            break
        except Exception as e:
            print(f"\n[오류] {e}")
            time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description='KeywordV2 - 네이버 키워드 순위 체크')
    parser.add_argument('--watch', action='store_true', help='스프레드시트 버튼 감지 모드')
    parser.add_argument('--setup', action='store_true', help='스프레드시트 초기 세팅')
    args = parser.parse_args()

    if args.setup:
        print("스프레드시트 초기 세팅 중...")
        setup_sheet()
        print("완료! 스프레드시트에 키워드를 입력하세요.")
    elif args.watch:
        watch_mode()
    else:
        check_all_keywords()


if __name__ == '__main__':
    main()
