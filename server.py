# server.py - KeywordV2 웹 서버 (Render 배포용)
# 스프레드시트 Apps Script에서 HTTP로 직접 호출

import os
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from sheet import read_keywords, write_results, get_spreadsheet
from scraper import run_check
from telegram_notify import send_report
from datetime import datetime
import random
import time
import re

app = Flask(__name__)

# 중복 실행 방지
checking_lock = threading.Lock()
is_checking = False


def _fill_previous_values(results):
    """스프레드시트의 E열(현재순위)을 D열(이전순위)로 이동 + 변동 계산"""
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return
    try:
        worksheet = spreadsheet.worksheet('키워드')
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


def do_check(keywords):
    """키워드 순위 체크 실행"""
    results = []
    for i, kw in enumerate(keywords, 1):
        print(f"[{i}/{len(keywords)}] '{kw['keyword']}' 체크 중...")
        try:
            status, rank, section = run_check(kw['keyword'], kw['url'], kw['title'])
        except Exception as e:
            print(f"  오류: {e}")
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
            'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        })

        if i < len(keywords):
            time.sleep(random.uniform(3, 6))

    _fill_previous_values(results)
    write_results(results)
    return results


def run_check_async(keywords, send_telegram=True):
    """백그라운드에서 순위 체크 실행"""
    global is_checking
    try:
        results = do_check(keywords)
        if send_telegram and results:
            send_report(results)
        print(f"체크 완료: {len(results)}개 키워드")
    except Exception as e:
        print(f"체크 오류: {e}")
    finally:
        is_checking = False


@app.route('/')
def index():
    return 'KeywordV2 서버 가동 중'


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'checking': is_checking})


@app.route('/check/all', methods=['POST'])
def check_all():
    """전체 키워드 순위 체크"""
    global is_checking

    # API 키 검증
    api_key = request.headers.get('X-API-Key') or request.args.get('key')
    expected_key = os.environ.get('API_KEY', '')
    if expected_key and api_key != expected_key:
        return jsonify({'error': '인증 실패'}), 401

    if is_checking:
        return jsonify({'message': '이미 체크가 진행 중입니다. 잠시 후 다시 시도해주세요.'}), 429

    keywords = read_keywords()
    if not keywords:
        return jsonify({'message': '체크할 키워드가 없습니다.'}), 404

    is_checking = True
    thread = threading.Thread(target=run_check_async, args=(keywords,))
    thread.start()

    return jsonify({
        'message': f'{len(keywords)}개 키워드 순위 체크를 시작합니다. 완료되면 스프레드시트에 결과가 업데이트됩니다.',
        'keyword_count': len(keywords)
    })


@app.route('/check/selected', methods=['POST'])
def check_selected():
    """선택한 행의 키워드만 체크"""
    global is_checking

    api_key = request.headers.get('X-API-Key') or request.args.get('key')
    expected_key = os.environ.get('API_KEY', '')
    if expected_key and api_key != expected_key:
        return jsonify({'error': '인증 실패'}), 401

    if is_checking:
        return jsonify({'message': '이미 체크가 진행 중입니다.'}), 429

    data = request.get_json() or {}
    start_row = data.get('start_row', 2)
    end_row = data.get('end_row', start_row)

    all_keywords = read_keywords()
    keywords = [kw for kw in all_keywords if start_row <= kw['row'] <= end_row]

    if not keywords:
        return jsonify({'message': '해당 행에 키워드가 없습니다.'}), 404

    is_checking = True
    thread = threading.Thread(target=run_check_async, args=(keywords, False))
    thread.start()

    keyword_names = [kw['keyword'] for kw in keywords]
    return jsonify({
        'message': f'{len(keywords)}개 키워드 체크를 시작합니다.',
        'keywords': keyword_names
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
