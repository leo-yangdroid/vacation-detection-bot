"""
Slack Bolt 앱 - 휴가 메시지 감지 → PagerDuty 온콜 + Jira 리그레이션 확인 → 스레드 답글
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
from jira_regression import get_regression_assignees_for_dates

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


def _is_same_user(slack_username: str, pd_or_jira_name: str) -> bool:
    """
    Slack username과 PagerDuty/Jira name 비교
    예) slack: "hashy.tag"  name: "hashy.tag(해시)" or "해시(hashy.tag)/팀명" → True
    """
    if not slack_username or not pd_or_jira_name:
        return False
    return slack_username.lower() in pd_or_jira_name.lower()


def _build_reply(dates_oncall: dict, regression_by_friday: dict, poster_username: str) -> str:
    """
    dates_oncall: {"2026-05-28": {"aos": {"name":..,"email":..}, "ios": {...}}}
    regression_by_friday: {date(2026,5,30): {"display_name":..,"slack_username":..,"issue_key":..,"friday":..}}
    poster_username: 휴가 올린 사람의 Slack username
    """
    warnings = []
    blocks = []

    # ── 온콜 섹션 ──
    for d_str, platforms in sorted(dates_oncall.items()):
        d = date.fromisoformat(d_str)
        label = _date_label(d)
        lines = [f"*{label}*"]

        for platform, oncall in platforms.items():
            if oncall is None:
                lines.append(f">:red_circle: {platform}: 없음")
                continue

            name = oncall["name"]
            if _is_same_user(poster_username, name):
                lines.append(f">:warning: {platform}: {name}  ← *본인*")
                warnings.append(f"• {label} {platform} 온콜")
            else:
                lines.append(f">{platform}: {name}")

        blocks.append("\n".join(lines))

    oncall_section = "📋 *온콜 확인 결과*\n\n" + "\n\n".join(blocks)

    # ── 리그레이션 섹션 ──
    regression_lines = []
    for friday, assignee in sorted(regression_by_friday.items()):
        friday_label = _date_label(friday)

        if assignee is None:
            regression_lines.append(f"*{friday_label} 주*  >담당자 없음 (티켓 미등록)")
            continue

        name = assignee["display_name"]
        issue_key = assignee["issue_key"]

        if _is_same_user(poster_username, assignee["slack_username"]):
            regression_lines.append(f"*{friday_label} 주*  (<{_jira_url(issue_key)}|{issue_key}>)\n>:warning: {name}  ← *본인*")
            warnings.append(f"• {friday_label} 리그레이션 테스트")
        else:
            regression_lines.append(f"*{friday_label} 주*  (<{_jira_url(issue_key)}|{issue_key}>)\n>{name}")

    regression_section = ""
    if regression_lines:
        regression_section = (
            "\n\n🧪 *리그레이션 테스트 담당자*\n\n"
            + "\n\n".join(regression_lines)
            + "\n\n_※ 테스트 완료 후 <https://www.notion.so/croquis/AOS-KPI-5f0d9190fbc34ff9959c034d9cb04136|AOS KPI 노션>에 수치도 입력해 주세요!_"
        )

    # ── 경고 섹션 ──
    warning_section = ""
    if warnings:
        warning_section = "\n\n⚠️ *일정 변경 필요!*\n" + "\n".join(warnings) + "\n담당자를 변경해 주세요."

    return oncall_section + regression_section + warning_section


def _jira_url(issue_key: str) -> str:
    return f"https://croquis.atlassian.net/browse/{issue_key}"


@app.event("message")
def handle_message(event, client, say, logger):
    # 봇 메시지만 무시
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

    if not parsed["is_vacation"] or not parsed["dates"]:
        logger.info(f"⏭ 휴가 공지 아님: {parsed.get('reason')}")
        return

    # 작성자 Slack username
    poster_username = _get_slack_username(client, event.get("user", ""))
    logger.info(f"👤 작성자: {poster_username}")

    dates = [date.fromisoformat(d) for d in parsed["dates"]]

    # PagerDuty 온콜 조회
    dates_oncall = {}
    for d in dates:
        try:
            platforms = get_oncall_by_platform(d)
            logger.info(f"🔍 온콜 {d}: {platforms}")
            dates_oncall[d.isoformat()] = platforms
        except Exception as e:
            logger.error(f"❌ PagerDuty 조회 실패 ({d}): {e}", exc_info=True)
            say(text="⚠️ PagerDuty 조회 중 오류가 발생했어요.", thread_ts=event["ts"])
            return

    # Jira 리그레이션 담당자 조회
    regression_by_friday = {}
    try:
        regression_by_friday = get_regression_assignees_for_dates(dates)
        logger.info(f"🧪 리그레이션: {regression_by_friday}")
    except Exception as e:
        logger.warning(f"⚠️ Jira 조회 실패 (무시하고 계속): {e}")

    reply = _build_reply(dates_oncall, regression_by_friday, poster_username)
    thread_ts = event.get("thread_ts") or event["ts"]
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
