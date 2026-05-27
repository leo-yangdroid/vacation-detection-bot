"""
Claude CLI로 메시지에서 휴가 여부 + 날짜 추출
(API Key 불필요 — claude CLI 인증 사용)
"""

import json
import subprocess
from datetime import date
from typing import Optional


def parse_vacation(text: str, today: Optional[date] = None) -> dict:
    """
    메시지가 휴가 공지인지 판단하고 날짜를 추출합니다.

    Returns:
        {
            "is_vacation": bool,
            "dates": ["2026-05-28", "2026-05-29"],
            "reason": "판단 근거 한 줄"
        }
    """
    if today is None:
        today = date.today()

    prompt = f"""오늘 날짜: {today.isoformat()} ({today.strftime('%Y년 %m월 %d일')})

다음 Slack 메시지가 **앞으로 있을 휴가/연차/반차를 공지하는 메시지**인지 판단하고 날짜를 추출하세요.

✅ 해당하는 경우: "5/28 연차입니다", "내일 반차 씁니다", "이번주 금요일 휴가"
❌ 해당하지 않는 경우: 스탠드업에서 "어제 휴가였어요", 보고서에서 "직전 업무일: 휴가"

메시지:
{text}

JSON만 반환하세요 (설명 없이):
{{"is_vacation": true/false, "dates": ["YYYY-MM-DD"], "reason": "한 줄 근거"}}"""

    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True, text=True, timeout=30
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI 실패: {result.stderr}")

    cli_output = json.loads(result.stdout)
    raw = cli_output["result"].strip()

    # 마크다운 코드블록 제거
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    parsed = json.loads(raw)
    return {
        "is_vacation": bool(parsed.get("is_vacation", False)),
        "dates": parsed.get("dates", []),
        "reason": parsed.get("reason", ""),
    }
