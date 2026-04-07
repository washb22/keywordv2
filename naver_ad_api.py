# naver_ad_api.py - 네이버 광고 API 검색량 조회
# 필요 환경변수: NAVER_AD_API_KEY, NAVER_AD_SECRET_KEY, NAVER_AD_CUSTOMER_ID

import os
import time
import hmac
import hashlib
import base64
import requests

BASE_URL = "https://api.searchad.naver.com"


def _signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    sig = hmac.new(secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(sig).decode("utf-8")


def _headers(method, uri):
    api_key = os.environ.get("NAVER_AD_API_KEY", "")
    secret_key = os.environ.get("NAVER_AD_SECRET_KEY", "")
    customer_id = os.environ.get("NAVER_AD_CUSTOMER_ID", "")
    if not (api_key and secret_key and customer_id):
        return None
    timestamp = str(int(time.time() * 1000))
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": api_key,
        "X-Customer": customer_id,
        "X-Signature": _signature(timestamp, method, uri, secret_key),
    }


_cache = {}
_last_call_time = 0.0


def get_search_volume(keyword: str) -> int:
    """PC + 모바일 월간 검색량 합산. 실패 시 0 반환. 429 시 재시도."""
    global _last_call_time
    if keyword in _cache:
        return _cache[keyword]

    uri = "/keywordstool"

    # Rate limit 방지: 마지막 호출로부터 최소 0.3초 대기
    now = time.time()
    elapsed = now - _last_call_time
    if elapsed < 0.3:
        time.sleep(0.3 - elapsed)

    # 최대 3회 재시도 (429 시 지수 backoff)
    max_retries = 3
    for attempt in range(max_retries):
        headers = _headers("GET", uri)
        if not headers:
            print("[광고API] 환경변수 없음 - 검색량 조회 건너뜀")
            _cache[keyword] = 0
            return 0

        try:
            params = {"hintKeywords": keyword.replace(" ", ""), "showDetail": "1"}
            r = requests.get(BASE_URL + uri, headers=headers, params=params, timeout=10)
            _last_call_time = time.time()

            if r.status_code == 429:
                wait = (attempt + 1) * 2  # 2초, 4초, 6초
                print(f"[광고API] '{keyword}' 429 Too Many Requests - {wait}초 대기 후 재시도 ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue

            if r.status_code != 200:
                print(f"[광고API] '{keyword}' 조회 실패 ({r.status_code}): {r.text[:120]}")
                _cache[keyword] = 0
                return 0
            break
        except Exception as e:
            print(f"[광고API] '{keyword}' 네트워크 오류: {e}")
            _cache[keyword] = 0
            return 0
    else:
        # 재시도 모두 실패
        print(f"[광고API] '{keyword}' 재시도 {max_retries}회 모두 실패")
        _cache[keyword] = 0
        return 0

    try:

        data = r.json()
        rows = data.get("keywordList") or []
        # 입력 키워드와 정확히 일치하는 것 우선
        target = keyword.replace(" ", "").lower()
        match = None
        for row in rows:
            rel = (row.get("relKeyword") or "").replace(" ", "").lower()
            if rel == target:
                match = row
                break
        if not match and rows:
            match = rows[0]
        if not match:
            _cache[keyword] = 0
            return 0

        pc = match.get("monthlyPcQcCnt", 0)
        mo = match.get("monthlyMobileQcCnt", 0)
        # "< 10" 같은 문자열도 옴
        def _to_int(v):
            if isinstance(v, int):
                return v
            s = str(v).strip().replace(",", "")
            if s.startswith("<"):
                return 0
            try:
                return int(s)
            except ValueError:
                return 0

        total = _to_int(pc) + _to_int(mo)
        _cache[keyword] = total
        return total
    except Exception as e:
        print(f"[광고API] '{keyword}' 오류: {e}")
        _cache[keyword] = 0
        return 0
