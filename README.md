# 회의록 액션 아이템 추출기

한국어 회의록을 입력받아 **액션 아이템 / 보류 항목 / 미해결 질문**을 구조화해 출력하는 Python CLI 도구입니다.  
런타임에 Google Gemini API(`gemini-2.5-flash`)를 호출하며, LLM 출력을 스키마 검증 및 근거 인용 확인으로 검증합니다.

---

## 빠른 시작

### 1. 환경 설정

```bash
# 저장소 클론
git clone <repo-url>
cd snd_homework

# 의존성 설치
pip install -r requirements.txt

# API 키 설정 (.env 파일 생성 후 키 입력)
cp .env.example .env
# 키 발급: https://aistudio.google.com/app/apikey
```

### 2. 실행

```bash
# 기본 실행 — 터미널 출력 + result.json 저장
python extractor.py --export-json result.json

# 다른 회의록 파일 지정
python extractor.py my_meeting.md --export-json result.json

# 터미널 출력만 (파일 저장 없음)
python extractor.py

# 검증 경고 없이 출력
python extractor.py --export-json result.json --no-validation-warnings
```

### 3. Smoke Test 실행 (LLM 없이)

```bash
python smoke_test.py
```

---

## 출력 파일

| 파일 | 생성 조건 | 위치 |
|------|-----------|------|
| `result.json` | `--export-json result.json` 옵션 지정 시 | 프로젝트 루트 |
| `logs/YYYY-MM-DD_HH-MM-SS.log` | 매 실행마다 자동 생성 | `logs/` 폴더 |

---

## 출력 예시

```
════════════════════════════════════════════════════════════
  📋 회의록 액션 아이템 추출 결과
════════════════════════════════════════════════════════════

🎯 액션 아이템 (5개)
────────────────────────────────────────────────────────────

[1] 백엔드 필터 PR 올리기
  담당자  : 준호
  마감일  : 금요일 오전
  신뢰도  : 🟢 high
  판단근거: 담당자(준호)와 마감일(금요일 오전) 모두 명확히 언급됨
  근거    : "금요일 오전까지 백엔드 필터 PR을 올리겠습니다."

[2] 프론트 검색창/결과 리스트 구현
  담당자  : 서연
  마감일  : 목요일 오후
  신뢰도  : 🟢 high
  판단근거: 담당자(서연)와 마감일(목요일 오후) 모두 명확히 언급됨
  근거    : "목요일 오후까지 검색창과 결과 리스트를 붙이겠습니다."
...

🚫 보류/제외 항목 (4개)
❓ 미해결 질문 (2개)
🔍 검증 결과
  ✅ action_items_>=4
  ✅ deferred_items_>=3
  ✅ open_questions_>=1
```

---

## 파일 구조

```
snd_homework/
├── extractor.py          # 메인 CLI 도구
├── smoke_test.py         # 검증 레이어 단위 테스트 (LLM 불필요)
├── meeting_transcript.md # 샘플 회의록
├── requirements.txt
├── .env.example
├── .gitignore
├── logs/                 # 실행 로그 (자동 생성, git 제외)
├── README.md
└── INTERVIEW_HANDOFF.md
```

---

## 에러 처리

| 상황 | 동작 |
|------|------|
| API 키 없음 | 안내 메시지 출력 후 종료 |
| 인증 실패 | 키 확인 안내 후 종료 |
| LLM 빈 응답 (safety filter 등) | 안내 메시지 출력 후 종료 |
| JSON 파싱 실패 | 원문 500자 로그 출력 후 종료 |
| 최소 수량 미달 | 경고 출력 후 exit code 2 |

---

## 요구사항

- Python 3.10+
- `google-genai`, `python-dotenv` 패키지 (`pip install -r requirements.txt`)
- Google Gemini API 키 ([발급 받기](https://aistudio.google.com/app/apikey), 무료 티어 있음)