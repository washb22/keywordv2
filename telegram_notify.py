# telegram_notify.py - 텔레그램 알림 모듈

import os
import requests
from datetime import datetime


def send_telegram_message(text):
    """텔레그램 메시지 발송"""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    if not token or not chat_id:
        print("[텔레그램] BOT_TOKEN 또는 CHAT_ID 미설정 - 알림 스킵")
        return False

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
            timeout=10
        )
        if resp.status_code == 200:
            print("[텔레그램] 발송 성공")
            return True
        else:
            print(f"[텔레그램] 발송 실패: {resp.status_code}")
            return False
    except Exception as e:
        print(f"[텔레그램] 오류: {e}")
        return False


def send_report(results):
    """순위 체크 결과를 텔레그램 리포트로 발송"""
    if not results:
        return

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [f"<b>키워드 순위 리포트</b>", f"<i>{now_str}</i>", ""]

    # 우선순위별 그룹핑
    groups = {'상': [], '중': [], '하': []}
    for r in results:
        p = r.get('priority', '중')
        groups.get(p, groups['중']).append(r)

    for priority, items in groups.items():
        if not items:
            continue
        lines.append(f"<b>【{priority}】</b>")

        for r in items:
            keyword = r['keyword']
            raw_status = r.get('raw_status', '')
            rank = r.get('rank', '')
            change = r.get('change', '')

            if raw_status == '노출X':
                emoji = '❌'
                detail = '미노출'
            elif raw_status == '확인 실패':
                emoji = '⚠️'
                detail = '확인 실패'
            else:
                if isinstance(rank, int) and rank <= 3:
                    emoji = '🔥'
                elif isinstance(rank, int) and rank <= 7:
                    emoji = '✅'
                else:
                    emoji = '📍'
                detail = r.get('status', '')

            change_str = f' ({change})' if change and change != '-' else ''
            lines.append(f"{emoji} <b>{keyword}</b> — {detail}{change_str}")
        lines.append("")

    total = len(results)
    exposed = sum(1 for r in results if r.get('raw_status') not in ('노출X', '확인 실패'))
    lines.append(f"<b>총 {total}개 | 노출 {exposed}개 | 미노출 {total - exposed}개</b>")

    send_telegram_message("\n".join(lines))
