# sheet.py - 구글 스프레드시트 읽기/쓰기 모듈

import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# 스프레드시트 컬럼 구조
# A: 키워드 | B: 글 제목 | C: URL
# D: 이전 순위 | E: 현재 순위 | F: 변동 | G: 마지막 확인
# H: 체크 요청 (Apps Script 버튼용)


def get_client():
    """서비스 계정으로 gspread 클라이언트 생성"""
    key_path = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY', '')
    if not key_path:
        print("[시트] GOOGLE_SERVICE_ACCOUNT_KEY 환경변수 없음")
        return None
    try:
        if key_path.strip().startswith('{'):
            info = json.loads(key_path)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(key_path, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"[시트] 인증 실패: {e}")
        return None


def get_spreadsheet(spreadsheet_id=None):
    """스프레드시트 객체 반환. spreadsheet_id 지정 시 해당 시트, 미지정 시 env 기본값"""
    client = get_client()
    if not client:
        return None
    if not spreadsheet_id:
        spreadsheet_id = os.environ.get('GOOGLE_SPREADSHEET_ID', '')
    if not spreadsheet_id:
        print("[시트] GOOGLE_SPREADSHEET_ID 없음")
        return None
    try:
        return client.open_by_key(spreadsheet_id)
    except Exception as e:
        print(f"[시트] 스프레드시트 열기 실패: {e}")
        return None


def read_keywords(sheet_name='키워드', spreadsheet_id=None):
    """스프레드시트에서 키워드 목록 읽기

    Returns:
        list of dict: [{'priority': '상', 'keyword': '...', 'title': '...', 'url': '...', 'row': 2}, ...]
    """
    spreadsheet = get_spreadsheet(spreadsheet_id)
    if not spreadsheet:
        return []

    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        print(f"[시트] '{sheet_name}' 시트를 찾을 수 없습니다.")
        return []

    all_values = worksheet.get_all_values()
    if len(all_values) < 2:
        print("[시트] 데이터가 없습니다 (헤더만 있거나 비어있음)")
        return []

    keywords = []
    for i, row in enumerate(all_values[1:], start=2):  # 2행부터 (1행은 헤더)
        if len(row) < 3:
            continue
        keyword = row[0].strip()
        title = row[1].strip() if len(row) > 1 else ''
        url = row[2].strip() if len(row) > 2 else ''

        if not keyword or not url:
            continue

        keywords.append({
            'keyword': keyword,
            'title': title,
            'url': url,
            'row': i
        })

    print(f"[시트] {len(keywords)}개 키워드 로드 완료")
    return keywords


def write_results(results, sheet_name='키워드', spreadsheet_id=None):
    """순위 체크 결과를 스프레드시트에 기록

    Args:
        results: list of dict with keys: row, prev_status, prev_rank, status, rank, change, checked_at
    """
    spreadsheet = get_spreadsheet(spreadsheet_id)
    if not spreadsheet:
        return False

    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        print(f"[시트] '{sheet_name}' 시트를 찾을 수 없습니다.")
        return False

    try:
        # 배치 업데이트로 한 번에 처리 (API 호출 최소화)
        cells_to_update = []
        for r in results:
            row_num = r['row']
            cells_to_update.append(gspread.Cell(row_num, 4, r.get('prev_rank_display', '')))  # D: 이전 순위
            cells_to_update.append(gspread.Cell(row_num, 5, r.get('status', '')))             # E: 현재 순위
            cells_to_update.append(gspread.Cell(row_num, 6, r.get('change', '')))             # F: 변동
            cells_to_update.append(gspread.Cell(row_num, 7, r.get('checked_at', '')))         # G: 마지막 확인

        if cells_to_update:
            worksheet.update_cells(cells_to_update)
            print(f"[시트] {len(results)}개 키워드 결과 기록 완료")

        # 체크 요청 셀 초기화 (H1)
        worksheet.update_acell('H1', '')

        return True
    except Exception as e:
        print(f"[시트] 결과 기록 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def write_status_section(status_rows, sheet_name='키워드', spreadsheet_id=None, clear_all=False):
    """작업현황 표 K~P열 업데이트. J열(타겟 키워드)은 건드리지 않음.
    K: 검색량 | L: 카페1 | M: 카페2 | N: 카페3 | O: 현재순위 | P: 상태

    status_rows: list of dict {row, keyword, volume, cafes, current_rank, status}
        row: J열에서 찾은 타겟 키워드의 행 번호
    """
    spreadsheet = get_spreadsheet(spreadsheet_id)
    if not spreadsheet:
        return False
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        print(f"[시트] '{sheet_name}' 시트를 찾을 수 없습니다.", flush=True)
        return False

    try:
        # 헤더 작성 (J열 제외 K~P만)
        k_headers = ['검색량', '카페1', '카페2', '카페3', '현재순위', '상태']
        worksheet.update(range_name='K1:P1', values=[k_headers])
        # J1은 사용자가 직접 관리 (비어있으면 '키워드' 라벨만)
        try:
            j1_val = worksheet.acell('J1').value or ''
            if not j1_val.strip():
                worksheet.update_acell('J1', '키워드')
        except Exception:
            pass

        # 각 status_row를 K~P에 기록 (J열은 안 건드림)
        cells_to_update = []
        for r in status_rows:
            target_row = r.get('row')
            if not target_row:
                continue
            cafes = r.get('cafes') or []
            cafe1 = cafes[0] if len(cafes) > 0 else ''
            cafe2 = cafes[1] if len(cafes) > 1 else ''
            cafe3 = cafes[2] if len(cafes) > 2 else ''
            # K~P 열만 (J열 제외)
            row_values = [
                r.get('volume', '') if r.get('volume') else '',
                cafe1, cafe2, cafe3,
                r.get('current_rank', ''),
                r.get('status', ''),
            ]
            # K=11, L=12, ..., P=16
            for col_offset, val in enumerate(row_values):
                cells_to_update.append(gspread.Cell(target_row, 11 + col_offset, val))

        if cells_to_update:
            worksheet.update_cells(cells_to_update)

        # 헤더 서식 (J~P 전체)
        worksheet.format('J1:P1', {
            'textFormat': {'bold': True, 'foregroundColorStyle': {'rgbColor': {'red': 1, 'green': 1, 'blue': 1}}},
            'backgroundColor': {'red': 0.3, 'green': 0.6, 'blue': 0.4},
            'horizontalAlignment': 'CENTER',
        })

        print(f"[시트] 작업현황 {len(status_rows)}행 K~P 업데이트 완료", flush=True)
        return True
    except Exception as e:
        print(f"[시트] 작업현황 기록 실패: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False


def check_request_flag(sheet_name='키워드'):
    """스프레드시트에서 체크 요청 플래그 확인 (K1 셀)

    Returns:
        None: 요청 없음
        'all': 전체 체크 요청
        (start_row, end_row): 개별 체크 요청 (행 번호 범위)
    """
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return None
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        val = (worksheet.acell('H1').value or '').strip()

        if val == '체크 요청':
            return 'all'
        elif val.startswith('체크:'):
            # '체크:3' 또는 '체크:3-5' 형식
            rows_part = val.split(':')[1]
            if '-' in rows_part:
                start, end = rows_part.split('-')
                return (int(start), int(end))
            else:
                row = int(rows_part)
                return (row, row)
        return None
    except Exception:
        return None


def setup_sheet(sheet_name='키워드'):
    """스프레드시트 초기 세팅 (헤더 + 서식)"""
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return False

    try:
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=500, cols=8)

        # 헤더 작성
        headers = ['키워드', '글 제목', 'URL', '이전 순위', '현재 순위',
                   '변동', '마지막 확인', '체크 요청']
        worksheet.update(range_name='A1:H1', values=[headers])

        # 헤더 서식
        worksheet.format('A1:H1', {
            'textFormat': {'bold': True, 'fontSize': 11},
            'backgroundColor': {'red': 0.2, 'green': 0.4, 'blue': 0.7},
            'horizontalAlignment': 'CENTER',
            'textFormat': {'bold': True, 'foregroundColorStyle': {'rgbColor': {'red': 1, 'green': 1, 'blue': 1}}}
        })

        # 열 너비 힌트용 빈 행 (구글 시트에서 수동 조정 필요)
        worksheet.update_acell('H2', '')

        print(f"[시트] '{sheet_name}' 시트 초기 세팅 완료")
        return True
    except Exception as e:
        print(f"[시트] 초기 세팅 실패: {e}")
        return False
