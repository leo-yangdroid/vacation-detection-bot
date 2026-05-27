"""
Slack Bolt 앱 - 휴가 메시지 감지 → PagerDuty 온콜 확인 → 스레드 답글
"""

import logging
import os
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from llm_parser import parse_vacation
from pagerduty import get_oncall_by_platform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)


def _date_label(d: date) -> str:
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return f"{d.month}/{d.day}({weekdays[d.weekday()]})"


def _get_slack_username(client, user_id: str) -> str:
    """Slack 유저 ID → username (예: leo.yangdroid) 반환"""
    try:
        result = client.users_info(user=user_id)
        return result["user"].get("name", "")
    except Exception:
        return ""


def _is_same_user(slack_username: str, pagerduty_name: str) -> bool:
    """
    Slack username과 PagerDuty summary 비교
    예) slack: "leo.yangdroid"  pd: "leo.yangdroid(유양우)" → True
    """
    if not slack_username or not pagerduty_name:
        return False
    return pagerduty_name.lower().startswith(slack_username.lower())


def _build_reply(dates_oncall: dict, poster_username: str) -> str:
    """
    dates_oncall: {
        "2026-05-28": {
            "aos": {"name": "llewyn.62s(박종혁)", "email": "..."},
            "ios": {"name": "dew.0601", "email": "..."},
        }
    }
    poster_username: 휴가 올린 사람의 Slack username
    """
    blocks = []
    conflict_dates = []

    for d_str, platforms in sorted(dates_oncall.items()):
        d = date.fromisoformat(d_str)
        label = _date_label(d)

        lines = [f"*{label}*"]
        is_conflict = False

        for platform, oncall in platforms.items():
            if oncall is None:
                lines.append(f">:red_circle: {platform}: 없음")
                continue

            name = oncall["name"]

            if _is_same_user(poster_username, name):
                lines.append(f">:warning: {platform}: {name}  ← *본인*")
                is_conflict = True
            else:
                lines.append(f">{platform}: {name}")

        if is_conflict:
            conflict_dates.append(label)

        blocks.append("\n".join(lines))

    reply = "📋 *온콜 확인 결과*\n\n" + "\n\n".join(blocks)

    if conflict_dates:
        dates_str = ", ".join(conflict_dates)
        reply += f"\n\n⚠️ *온콜 일정 변경 필요!*\n{dates_str}에 본인이 온콜입니다. 담당자를 변경해 주세요."

    return reply


@app.event("message")
def handle_message(event, client, say, logger):
    # 봇 메시지만 무시 (무한루프 방지), 스레드 댓글은 허용
    if event.get("bot_id"):
        return

    text: str = event.get("text", "")
    if not text:
        return

    logger.info(f"📨 메시지 수신: {text[:60]!r}")

    # LLM으로 휴가 여부 + 날짜 판단
    try:
        parsed = parse_vacation(text)
    except Exception as e:
        logger.error(f"❌ LLM 파싱 실패: {e}", exc_info=True)
        return

    logger.info(f"🤖 LLM 판단: {parsed}")

    if not parsed["is_vacation"]:
        logger.info(f"⏭ 휴가 공지 아님: {parsed['reason']}")
        return

    if not parsed["dates"]:
        logger.info("⚠️ 날짜 추출 실패")
        return

    # 메시지 작성자 username 조회
    poster_username = _get_slack_username(client, event.get("user", ""))
    logger.info(f"👤 작성자 username: {poster_username}")

    # PagerDuty 조회
    dates_oncall = {}
    for d_str in parsed["dates"]:
        try:
            d = date.fromisoformat(d_str)
            platforms = get_oncall_by_platform(d)
            logger.info(f"🔍 {d_str} 온콜: {platforms}")
            dates_oncall[d_str] = platforms
        except Exception as e:
            logger.error(f"❌ PagerDuty 조회 실패 ({d_str}): {e}", exc_info=True)
            say(text="⚠️ PagerDuty 조회 중 오류가 발생했어요.", thread_ts=event["ts"])
            return

    reply = _build_reply(dates_oncall, poster_username)
    thread_ts = event.get("thread_ts") or event["ts"]
    logger.info(f"💬 답글 전송: thread_ts={thread_ts}")
    say(text=reply, thread_ts=thread_ts)


if __name__ == "__main__":
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if app_token:
        handler = SocketModeHandler(app, app_token)
        logger.info("⚡ Socket Mode 시작")
        handler.start()
    else:
        logger.info("🌐 HTTP Mode 시작 (port 3000)")
        app.start(port=int(os.environ.get("PORT", 3000)))
