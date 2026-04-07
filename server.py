# server.py - KeywordV2 웹 서버 (Render 배포용)
# 스프레드시트 Apps Script에서 HTTP로 직접 호출

import os
import threading
import queue
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from sheet import read_keywords, write_results, get_spreadsheet, write_status_section
from scraper import run_check, get_top_cafes, create_driver
from telegram_notify import send_report
from naver_ad_api import get_search_volume
from datetime import datetime, timezone, timedelta
import random
import time
import re

KST = timezone(timedelta(hours=9))


def now_kst():
    return datetime.now(KST)

app = Flask(__name__)

# 작업 큐 + 워커 스레드
task_queue = queue.Queue()
current_task = None  # 현재 진행 중인 작업 정보


def _fill_previous_values(results, sheet_name='키워드', spreadsheet_id=None):
    """스프레드시트의 E열(현재순위)을 D열(이전순위)로 이동 + 변동 계산"""
    spreadsheet = get_spreadsheet(spreadsheet_id)
    if not spreadsheet:
        return
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        all_values = worksheet.get_all_values()
        for r in results:
            row_idx = r['row'] - 1
            if row_idx < len(all_values):
                row_data = all_values[row_idx]
                prev_display = row_data[4] if len(row_data) > 4 else ''
                r['prev_rank_display'] = prev_display
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
        print(f"[이전값] 읽기 실패: {e}")


def get_all_sheet_names():
    """스프레드시트의 모든 시트 이름 반환"""
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return []
    return [ws.title for ws in spreadsheet.worksheets()]


def do_check(keywords, sheet_name='키워드', spreadsheet_id=None):
    """키워드 순위 체크 실행"""
    results = []
    for i, kw in enumerate(keywords, 1):
        print(f"[{sheet_name}] [{i}/{len(keywords)}] '{kw['keyword']}' 체크 중...", flush=True)
        try:
            status, rank, section = run_check(kw['keyword'], kw['url'], kw['title'])
        except Exception as e:
            print(f"  오류: {e}", flush=True)
            status, rank, section = '확인 실패', 999, None

        if status == '노출X':
            status_display = '미노출'
        elif rank and rank < 999:
            status_display = f'{section} {rank}위'
        else:
            status_display = status

        results.append({
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
        })

        if i < len(keywords):
            time.sleep(random.uniform(3, 6))

    _fill_previous_values(results, sheet_name, spreadsheet_id=spreadsheet_id)
    write_results(results, sheet_name, spreadsheet_id=spreadsheet_id)

    # 작업현황 표 (J~P열) 기록
    try:
        _build_and_write_status(results, keywords, sheet_name, spreadsheet_id)
    except Exception as e:
        print(f"[작업현황] 실패: {e}", flush=True)

    return results


def _build_and_write_status(results, keywords, sheet_name, spreadsheet_id):
    """작업현황 표 생성 및 J~P열 기록"""
    print(f"[작업현황] [{sheet_name}] 집계 시작...", flush=True)

    # 키워드별 고유 목록
    unique_keywords = []
    seen = set()
    for kw in keywords:
        k = kw['keyword']
        if k and k not in seen:
            seen.add(k)
            unique_keywords.append(k)

    # 검색량 (네이버 광고 API)
    volume_map = {}
    for k in unique_keywords:
        volume_map[k] = get_search_volume(k)
    print(f"[작업현황] 검색량 {len(volume_map)}개 조회 완료", flush=True)

    # 상위 카페 3개 (selenium)
    cafe_map = {}
    driver = None
    try:
        driver = create_driver()
        for i, k in enumerate(unique_keywords, 1):
            print(f"[카페추출] ({i}/{len(unique_keywords)}) '{k}'", flush=True)
            cafe_map[k] = get_top_cafes(driver, k, max_count=3)
            time.sleep(random.uniform(2, 4))
    except Exception as e:
        print(f"[카페추출] 드라이버 오류: {e}", flush=True)
    finally:
        if driver:
            driver.quit()

    status_rows = []
    for r in results:
        keyword = r['keyword']
        current_rank = r.get('status', '')
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

    write_status_section(status_rows, sheet_name, spreadsheet_id=spreadsheet_id or None)


def queue_worker():
    """큐에서 작업을 꺼내 순차적으로 처리하는 워커"""
    global current_task
    while True:
        task = task_queue.get()
        try:
            current_task = task
            keywords = task['keywords']
            sheet_name = task['sheet_name']
            send_telegram = task.get('send_telegram', False)

            spreadsheet_id = task.get('spreadsheet_id', '')

            print(f"[큐] [{sheet_name}] {len(keywords)}개 키워드 체크 시작 (대기열: {task_queue.qsize()}개 남음)")
            results = do_check(keywords, sheet_name, spreadsheet_id=spreadsheet_id or None)
            if send_telegram and results:
                send_report(results)
            print(f"[큐] [{sheet_name}] 체크 완료")
        except Exception as e:
            print(f"[큐] 오류: {e}")
        finally:
            current_task = None
            task_queue.task_done()


# 워커 스레드 시작
worker_thread = threading.Thread(target=queue_worker, daemon=True)
worker_thread.start()


@app.route('/')
def index():
    return 'KeywordV2 서버 가동 중'


@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'checking': current_task is not None,
        'queue_size': task_queue.qsize()
    })


@app.route('/check/all', methods=['POST'])
def check_all():
    """전체 키워드 순위 체크 (큐에 추가)"""
    api_key = request.headers.get('X-API-Key') or request.args.get('key')
    expected_key = os.environ.get('API_KEY', '')
    if expected_key and api_key != expected_key:
        return jsonify({'error': '인증 실패'}), 401

    data = request.get_json() or {}
    sheet_name = data.get('sheet_name', '키워드')
    spreadsheet_id = data.get('spreadsheet_id', '')  # 외부 시트 지원

    keywords = read_keywords(sheet_name, spreadsheet_id=spreadsheet_id or None)
    if not keywords:
        return jsonify({'message': f'[{sheet_name}] 체크할 키워드가 없습니다.'}), 404

    task_queue.put({
        'keywords': keywords,
        'sheet_name': sheet_name,
        'spreadsheet_id': spreadsheet_id,
        'send_telegram': True
    })

    queue_size = task_queue.qsize()
    if current_task:
        msg = f'[{sheet_name}] {len(keywords)}개 키워드가 대기열에 추가되었습니다. (현재 {current_task["sheet_name"]} 체크 중, 대기 {queue_size}건)'
    else:
        msg = f'[{sheet_name}] {len(keywords)}개 키워드 순위 체크를 시작합니다.'

    return jsonify({'message': msg, 'keyword_count': len(keywords)})


@app.route('/check/selected', methods=['POST'])
def check_selected():
    """선택한 행의 키워드만 체크 (큐에 추가)"""
    api_key = request.headers.get('X-API-Key') or request.args.get('key')
    expected_key = os.environ.get('API_KEY', '')
    if expected_key and api_key != expected_key:
        return jsonify({'error': '인증 실패'}), 401

    data = request.get_json() or {}
    start_row = data.get('start_row', 2)
    end_row = data.get('end_row', start_row)
    sheet_name = data.get('sheet_name', '키워드')
    spreadsheet_id = data.get('spreadsheet_id', '')

    all_keywords = read_keywords(sheet_name, spreadsheet_id=spreadsheet_id or None)
    keywords = [kw for kw in all_keywords if start_row <= kw['row'] <= end_row]

    if not keywords:
        return jsonify({'message': '해당 행에 키워드가 없습니다.'}), 404

    task_queue.put({
        'keywords': keywords,
        'sheet_name': sheet_name,
        'spreadsheet_id': spreadsheet_id,
        'send_telegram': False
    })

    keyword_names = [kw['keyword'] for kw in keywords]
    queue_size = task_queue.qsize()
    if current_task:
        msg = f'[{sheet_name}] {len(keywords)}개 키워드가 대기열에 추가되었습니다. (현재 {current_task["sheet_name"]} 체크 중, 대기 {queue_size}건)'
    else:
        msg = f'[{sheet_name}] {len(keywords)}개 키워드 체크를 시작합니다.'

    return jsonify({'message': msg, 'keywords': keyword_names})


def scheduled_check():
    """매일 자동 순위 체크 - 모든 시트를 큐에 추가"""
    print(f"[스케줄러] 자동 순위 체크 시작: {now_kst().strftime('%Y-%m-%d %H:%M:%S')}")
    sheet_names = get_all_sheet_names()
    if not sheet_names:
        print("[스케줄러] 시트 없음")
        return

    for sheet_name in sheet_names:
        keywords = read_keywords(sheet_name)
        if not keywords:
            continue
        task_queue.put({
            'keywords': keywords,
            'sheet_name': sheet_name,
            'send_telegram': True
        })
        print(f"[스케줄러] [{sheet_name}] {len(keywords)}개 키워드 큐에 추가")


# 스케줄러 설정 - 매일 새벽 6시(KST) = 21시(UTC)
scheduler = BackgroundScheduler()
scheduler.add_job(
    scheduled_check,
    CronTrigger(hour=21, minute=0, timezone='UTC'),  # KST 06:00
    id='daily_check',
    name='매일 새벽 6시 자동 체크'
)
scheduler.start()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
