"""
PagerDuty REST API v2 클라이언트
- Android / iOS 온콜 스케줄 날짜별 담당자 조회
"""

import os
from datetime import date, timedelta
from typing import List, Optional

import requests

PAGERDUTY_API_BASE = "https://api.pagerduty.com"

SCHEDULES = {
    "aos": os.getenv("PAGERDUTY_AOS_SCHEDULE_ID", "PIQG8OK"),
    "ios": os.getenv("PAGERDUTY_IOS_SCHEDULE_ID", "PEEV7ZX"),
}


def _headers() -> dict:
    token = os.getenv("PAGERDUTY_API_TOKEN")
    if not token:
        raise EnvironmentError("PAGERDUTY_API_TOKEN 환경변수가 설정되지 않았습니다.")
    return {
        "Authorization": f"Token token={token}",
        "Accept": "application/vnd.pagerduty+json;version=2",
    }


def _oncall_user_for_schedule(schedule_id: str, target_date: date) -> Optional[dict]:
    """
    특정 날짜(KST 기준 하루) 온콜 담당자 반환.
    스케줄 교체 시각 = KST 10:00 AM = UTC 01:00

    Returns:
        {"name": "llewyn.62s(박종혁)", "email": "llewyn.62s@kakaostyle.com"}
        온콜 없으면 None
    """
    since = target_date.isoformat() + "T01:00:00Z"
    until = target_date.isoformat() + "T14:59:59Z"

    url = (
        f"{PAGERDUTY_API_BASE}/oncalls"
        f"?schedule_ids[]={schedule_id}"
        f"&since={since}&until={until}&include[]=users"
    )
    resp = requests.get(url, headers=_headers(), timeout=10)
    resp.raise_for_status()

    oncalls = resp.json().get("oncalls", [])
    if not oncalls:
        return None

    user = oncalls[0].get("user", {})
    return {
        "name": user.get("summary") or user.get("name") or "알 수 없음",
        "email": user.get("email", ""),
    }


def get_oncall_by_platform(target_date: date) -> dict:
    """
    날짜의 AOS / iOS 온콜 담당자 각 1명씩 반환.

    Returns:
        {
            "aos": {"name": "llewyn.62s(박종혁)", "email": "llewyn.62s@kakaostyle.com"},
            "ios": {"name": "dew.0601", "email": "dew.0601@kakaostyle.com"},
        }
    """
    result = {}
    for platform, schedule_id in SCHEDULES.items():
        result[platform] = _oncall_user_for_schedule(schedule_id, target_date)
    return result
