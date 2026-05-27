"""
Jira REST API v3 - AOS 리그레이션 테스트 담당자 조회
- 부모 티켓: JQL로 자동 탐지 (매년 새 티켓 만들어도 코드 수정 불필요)
- 하위 이슈: [MM/DD] 패턴으로 해당 주 금요일 담당자 조회
"""

import os
import re
from datetime import date, timedelta
from typing import Optional

import requests

JIRA_BASE = "https://croquis.atlassian.net"

# 부모 티켓 캐시 (프로세스 재시작 전까지 유지)
_parent_key_cache: Optional[str] = None


def _auth() -> tuple:
    email = os.getenv("JIRA_EMAIL")
    token = os.getenv("JIRA_API_TOKEN")
    if not email or not token:
        raise EnvironmentError("JIRA_EMAIL 또는 JIRA_API_TOKEN이 설정되지 않았습니다.")
    return (email, token)


def _jira_search(jql: str, fields: list, max_results: int = 5) -> list:
    resp = requests.post(
        f"{JIRA_BASE}/rest/api/3/search/jql",
        auth=_auth(),
        json={"jql": jql, "maxResults": max_results, "fields": fields},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("issues", [])


def _get_regression_parent_key() -> Optional[str]:
    """
    현재 연도 AOS 리그레이션 부모 티켓 자동 탐지.
    매년 새 티켓([AOS 27'] 리그레이션 검증테스트)이 생겨도 자동으로 최신 티켓 사용.
    """
    global _parent_key_cache
    if _parent_key_cache:
        return _parent_key_cache

    issues = _jira_search(
        jql='project = APP AND summary ~ "[AOS" AND summary ~ "리그레이션 검증테스트" ORDER BY created DESC',
        fields=["summary"],
        max_results=1,
    )
    if not issues:
        return None

    _parent_key_cache = issues[0]["key"]
    return _parent_key_cache


def get_friday_of_week(d: date) -> date:
    """해당 주(월~일)의 금요일 반환"""
    days_to_friday = (4 - d.weekday()) % 7
    return d + timedelta(days=days_to_friday)


def extract_slack_username(jira_display_name: str) -> str:
    """
    'hashy(hashy.tag)/지그재그서비스앱개발팀' → 'hashy.tag'
    괄호 안의 Slack username 추출
    """
    match = re.search(r"\(([^)]+)\)", jira_display_name)
    return match.group(1) if match else jira_display_name


def get_regression_assignee(target_date: date) -> Optional[dict]:
    """
    target_date가 포함된 주의 금요일 리그레이션 테스트 담당자 반환.

    Returns:
        {
            "display_name": "해시(hashy.tag)/지그재그서비스앱개발팀",
            "slack_username": "hashy.tag",
            "issue_key": "APP-13610",
            "friday": date(2026, 5, 30),
        }
        담당자 없으면 None
    """
    parent_key = _get_regression_parent_key()
    if not parent_key:
        return None

    friday = get_friday_of_week(target_date)
    date_str = friday.strftime("%m/%d")  # "05/30"

    issues = _jira_search(
        jql=f'parent = {parent_key} AND summary ~ "{date_str}"',
        fields=["summary", "assignee"],
        max_results=1,
    )
    if not issues:
        return None

    issue = issues[0]
    assignee = issue["fields"].get("assignee")
    if not assignee:
        return {
            "display_name": "미배정",
            "slack_username": "",
            "issue_key": issue["key"],
            "friday": friday,
        }

    display_name = assignee.get("displayName", "알 수 없음")
    return {
        "display_name": display_name,
        "slack_username": extract_slack_username(display_name),
        "issue_key": issue["key"],
        "friday": friday,
    }


def get_regression_assignees_for_dates(dates: list) -> dict:
    """
    날짜 리스트에서 고유한 주(금요일)별 리그레이션 담당자 반환.
    같은 주의 날짜는 중복 제거.

    Returns:
        { date(2026, 5, 30): {...assignee info...} }
    """
    seen_fridays = set()
    result = {}

    for d in sorted(dates):
        friday = get_friday_of_week(d)
        if friday in seen_fridays:
            continue
        seen_fridays.add(friday)

        assignee = get_regression_assignee(d)
        result[friday] = assignee  # None이면 해당 주 이슈 없음

    return result
