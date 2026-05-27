# 🏖️ Vacation On-Call Bot

Slack 채널에 휴가/연차 메시지가 올라오면 **PagerDuty 온콜 일정**과 **Jira 리그레이션 테스트 담당자**를 자동으로 확인해 스레드에 답글을 달아주는 봇입니다.

본인이 온콜이거나 리그레이션 담당자인 경우 **변경 필요 경고**도 자동으로 알려줍니다.

<br>

## ✨ 기능

- 💬 Slack 메시지 / 스레드 댓글 모두 감지
- 🤖 Claude CLI로 휴가 공지 여부 및 날짜 자동 파싱 (LLM 기반, 오탐 방지)
- 📟 PagerDuty AOS / iOS 온콜 담당자 각 1명씩 조회 (KST 10:00 교대 기준)
- 🧪 Jira AOS 리그레이션 테스트 담당자 조회 (해당 주 금요일 기준)
  - JQL 자동 탐지로 매년 새 티켓 생성 시 코드 수정 불필요
- ⚠️ 본인이 온콜 또는 리그레이션 담당자인 경우 변경 필요 경고

<br>

## 📸 동작 예시

**채널 메시지:**
> 5/29 연차입니다!

**봇 스레드 답글:**
```
📋 온콜 확인 결과

5/29(금)
| aos: lena.dev
| ios: eden.jjh

🧪 리그레이션 테스트 담당자

5/29(금) 주  (APP-13805)
| 해시(hashy.tag)/지그재그서비스앱개발팀

※ 테스트 완료 후 AOS KPI 노션에 수치도 입력해 주세요!
```

**본인이 온콜 + 리그레이션 담당자인 경우:**
```
📋 온콜 확인 결과

6/6(금)
| ⚠️ aos: harry.magic  ← 본인
| ios: dew.0601

🧪 리그레이션 테스트 담당자

6/6(금) 주  (APP-13820)
| ⚠️ harry.magic  ← 본인

⚠️ 일정 변경 필요!
• 6/6(금) aos 온콜
• 6/6(금) 리그레이션 테스트
담당자를 변경해 주세요.
```

<br>

## 🛠️ 기술 스택

| 역할 | 기술 |
|------|------|
| Slack 연동 | [Slack Bolt for Python](https://slack.dev/bolt-python/) + Socket Mode |
| 휴가 감지 | [Claude CLI](https://claude.ai/code) (`claude -p`) |
| 온콜 조회 | [PagerDuty REST API v2](https://developer.pagerduty.com/api-reference/) |
| 리그레이션 담당자 조회 | [Jira REST API v3](https://developer.atlassian.com/cloud/jira/platform/rest/v3/) |

<br>

## 🚀 설치 및 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
cp .env.example .env
# .env 파일에 각 토큰 입력
```

| 변수 | 설명 | 발급 위치 |
|------|------|----------|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token | OAuth & Permissions |
| `SLACK_SIGNING_SECRET` | 요청 검증용 시크릿 | Basic Information |
| `SLACK_APP_TOKEN` | Socket Mode용 App Token | Socket Mode |
| `PAGERDUTY_API_TOKEN` | PagerDuty API Token | My Profile → API Access |
| `PAGERDUTY_AOS_SCHEDULE_ID` | Android 온콜 스케줄 ID | PagerDuty Schedules |
| `PAGERDUTY_IOS_SCHEDULE_ID` | iOS 온콜 스케줄 ID | PagerDuty Schedules |
| `JIRA_EMAIL` | Atlassian 계정 이메일 | - |
| `JIRA_API_TOKEN` | Jira API Token | [id.atlassian.com → Security → API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) |

### 3. Slack App 설정

**OAuth & Permissions → Bot Token Scopes:**
```
channels:history   chat:write   users:read
channels:join      chat:write.public
```

**Event Subscriptions → Subscribe to bot events:**
```
message.channels
```

**Socket Mode:** Enable → App-Level Token 발급 (`connections:write`)

### 4. 봇을 채널에 초대

```
/invite @봇이름
```

### 5. 실행

```bash
python3 app.py
```

<br>

## 📁 프로젝트 구조

```
vacation-oncall-bot/
├── app.py              # Slack Bolt 앱 — 메시지 감지 및 답글
├── llm_parser.py       # Claude CLI로 휴가 여부 + 날짜 파싱
├── pagerduty.py        # PagerDuty API AOS/iOS 온콜 담당자 조회
├── jira_regression.py  # Jira API 리그레이션 테스트 담당자 조회
├── requirements.txt
├── .env.example        # 환경변수 템플릿
└── .gitignore
```

<br>

## 🔍 지원하는 휴가 메시지 형식

LLM 기반 파싱이라 자연어를 자유롭게 인식합니다.

| 메시지 예시 | 감지 |
|------------|------|
| `5/28 연차입니다` | ✅ |
| `내일 반차 씁니다` | ✅ |
| `이번주 금요일 휴가` | ✅ |
| `5/28~5/30 자리 비웁니다` | ✅ |
| `어제 휴가였어요` (과거) | ❌ 무시 |
| 스탠드업에서 `직전 업무일: 휴가` | ❌ 무시 |

<br>

## 🔄 매년 자동 대응

리그레이션 티켓은 JQL로 자동 탐지하므로 **연도가 바뀌어도 코드 수정이 필요 없습니다.**

```
# 항상 가장 최근에 생성된 티켓을 사용
project = APP AND summary ~ "[AOS" AND summary ~ "리그레이션 검증테스트"
ORDER BY created DESC
```

새 연도 티켓(`[AOS 27'] 리그레이션 검증테스트`)이 생성되는 순간 자동으로 전환됩니다.
