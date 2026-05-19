# INTERVIEW_HANDOFF.md

## Product Specification

### Core user problem
한국어 회의록에는 액션 아이템이 산재해 있지만, 담당자·마감일·근거가 흩어져 있어 회의 후 후속 조치를 놓치기 쉽다. 이 도구는 회의록을 입력받아 **누가, 무엇을, 언제까지 해야 하는지**를 구조화된 형태로 추출하고, 이번 범위에서 제외된 항목과 미해결 질문도 함께 정리한다.

### Target user and workflow
- **사용자**: 회의 후 액션 아이템을 정리하는 팀원 또는 PM
- **입력**: 한국어 회의록 텍스트 파일 (.md 또는 .txt)
- **출력**: 터미널 출력(액션 아이템 / 보류 항목 / 미해결 질문) + 선택적 JSON export
- **워크플로우**: `python extractor.py meeting_transcript.md` → 결과 확인 → 필요시 JSON 저장

### Functional requirements
1. 한국어 회의록 파일을 로드한다
2. 런타임에 Google Gemini API를 호출해 추출한다
3. 각 액션 아이템에 `owner / task / deadline / confidence / evidence_quote` 필드를 포함한다
4. 담당자·마감일이 불명확하면 `unknown`으로 표시하고 추측하지 않는다
5. LLM 출력을 스키마 검증 + 근거 인용 확인으로 검증한다
6. 보류/제외 항목과 미해결 질문도 구조화해 출력한다
7. `--export-json` 옵션으로 JSON 파일 저장을 지원한다
8. 최소 4개 액션 아이템, 3개 보류 항목, 1개 미해결 질문을 추출한다

### Input and output contract

**Input**
- 파일 형식: `.md` 또는 `.txt` (UTF-8)
- 최소 요건: 한국어 텍스트로 된 회의록

**Output schema**
```json
{
  "action_items": [
    {
      "owner": "string | 'unknown'",
      "task": "string",
      "deadline": "string | 'unknown'",
      "confidence": "'high' | 'medium' | 'low'",
      "confidence_reason": "string (confidence 산정 이유 한 문장)",
      "evidence_quote": "string (회의록 원문 그대로)",
      "notes": "string (optional)"
    }
  ],
  "deferred_items": [
    {
      "item": "string",
      "reason": "string",
      "evidence_quote": "string"
    }
  ],
  "open_questions": [
    {
      "question": "string",
      "raised_by": "string | 'unknown'",
      "evidence_quote": "string"
    }
  ]
}
```

**Error states**
- API 키 없음 → `exit(1)` + 안내 메시지
- 인증 실패 → `exit(1)`
- 네트워크 오류 → `exit(1)`
- JSON 파싱 실패 → `exit(1)` + 원문 출력
- 최소 수량 미달 → `exit(2)` + 경고 메시지

### LLM behavior contract

**사용 위치**: `extractor.py` → `call_llm()` 함수, 런타임에 매 실행마다 호출

**모델**: `gemini-2.5-flash` (Google Gemini API)

**System prompt 핵심 규칙**:
- 회의록에 명시된 내용만 추출 (추측 금지)
- `owner` / `deadline` 불명확 시 반드시 `"unknown"` 사용
- `evidence_quote`는 원문 그대로 (요약·변형 금지)
- JSON만 출력 (마크다운 코드블록 금지)

**confidence 산정 기준**:
- `high`: 담당자 + 할 일 + 마감일 모두 명확
- `medium`: 셋 중 하나가 불명확
- `low`: 담당자·마감일 모두 불명확하거나 발언이 모호

**LLM이 하면 안 되는 것**:
- 회의록에 없는 담당자나 마감일 추측
- evidence_quote 요약 또는 변형
- JSON 외 텍스트 출력

### Non-goals
- 전체 회의록 관리 제품
- 캘린더 / Slack / Notion 연동
- 사용자 인증 및 데이터베이스
- 음성 인식 및 화자 분리
- 한국어 형태소 분석 / NLP 파서
- 대규모 문서 처리 / 배치 처리
- 미려한 UI

### Acceptance criteria
1. `python extractor.py meeting_transcript.md` 실행 시 오류 없이 결과 출력
2. 액션 아이템 4개 이상, 보류 항목 3개 이상, 미해결 질문 1개 이상 추출
3. 모든 액션 아이템에 `evidence_quote` 포함
4. 담당자·마감일 불명확한 항목에 `unknown` 표시
5. `python smoke_test.py` 실행 시 10/10 통과
6. `--export-json` 옵션으로 유효한 JSON 파일 생성

---

## Implementation Plan

### Planned architecture
```
extractor.py (단일 파일 CLI)
├── call_llm()           — Google Gemini API 호출
├── parse_llm_output()   — JSON 파싱 + 마크다운 코드블록 제거 + 줄바꿈 처리
├── validate_action_item() — 개별 아이템 검증
├── validate_results()   — 전체 결과 검증 + 최소 수량 체크
├── print_results()      — 터미널 출력 포맷터
└── main()               — CLI 진입점 (argparse)

smoke_test.py            — 검증 레이어 단위 테스트 (LLM 불필요)
meeting_transcript.md    — 샘플 회의록
```

### Implementation steps
1. 프로젝트 디렉토리 생성 및 `requirements.txt` 작성
2. `meeting_transcript.md` 샘플 파일 준비
3. LLM 시스템 프롬프트 및 추출 프롬프트 설계
4. `call_llm()` — Google Gemini SDK 호출 + 에러 처리
5. `parse_llm_output()` — JSON 파싱 + 코드블록 제거
6. `validate_action_item()` — 필수 필드 / confidence / evidence_quote 검증
7. `validate_results()` — 전체 검증 + 최소 수량 체크
8. `print_results()` — 터미널 출력 포맷터
9. `main()` — argparse CLI, API 키 확인, 파일 로드
10. `smoke_test.py` 작성 및 실행 검증
11. README / INTERVIEW_HANDOFF.md 작성

### Verification and guardrails

| 검증 항목 | 방법 |
|-----------|------|
| 필수 필드 존재 | `REQUIRED_ACTION_FIELDS` set 체크 |
| confidence 값 | `VALID_CONFIDENCE` set 멤버십 체크 |
| evidence_quote 원문 포함 | 공백 정규화 후 `in` 연산자로 회의록 원문과 대조 |
| deadline=unknown + confidence=high 불일치 | 결정적 규칙으로 경고 |
| JSON 파싱 실패 | try/except + 원문 출력 |
| LLM 마크다운 코드블록 | regex로 제거 후 파싱 |
| LLM 응답 내 줄바꿈 | while 루프로 반복 제거 후 파싱 |
| 최소 수량 미달 | `exit(2)` |

### Test plan
- `smoke_test.py`: LLM 없이 실행 가능한 10개 단위 테스트
  - 정상 아이템 통과
  - 필수 필드 누락 감지
  - 잘못된 confidence 감지
  - 근거 없는 evidence_quote 감지
  - deadline=unknown + confidence=high 경고
  - 정상 JSON 파싱
  - 마크다운 코드블록 포함 JSON 파싱
  - 최소 수량 검증 (3개 체크)
- 수동 smoke check: 실제 API 호출 후 출력 리뷰

---

## Ambiguities and Assumptions

### Ambiguities
- `deadline`의 표현이 "금요일 오전"처럼 상대적 날짜일 경우 구체적 날짜로 변환할지 여부 → 원문 표현 그대로 유지하기로 결정
- 같은 사람이 여러 액션 아이템을 말했을 때 하나로 합칠지 분리할지 → 분리 (각 발언을 독립적으로 처리)
- 마감일이 "오늘 안에"처럼 모호한 경우 → `unknown`이 아닌 원문 그대로 유지

### Assumptions
- 입력 파일은 UTF-8 인코딩
- 회의록의 화자는 `이름:` 형식으로 구분됨
- LLM이 한국어 회의록을 충분히 이해할 수 있음 (Gemini 2.5 Flash 기준)
- 단일 파일 실행 환경 (멀티프로세싱 불필요)

---

## Implementation Notes

### Main files created or changed
- `extractor.py` — 메인 CLI (350줄)
- `smoke_test.py` — 검증 단위 테스트 (180줄)
- `meeting_transcript.md` — 샘플 회의록
- `requirements.txt`, `.env.example`, `README.md`, `INTERVIEW_HANDOFF.md`

### Key design choices
1. **단일 파일 CLI**: 패키지 구조 없이 파일 하나를 그대로 실행할 수 있어서 환경 구성이 단순하고, 인터뷰어가 전체 흐름을 한 파일에서 리뷰할 수 있음. 이 규모에서 모듈 분리는 오버엔지니어링이라고 판단. 대신 검증 함수들을 독립적으로 분리하여 `smoke_test.py`에서 LLM 없이도 테스트할 수 있게 설계
2. **검증을 별도 레이어로 분리**: `validate_action_item()` / `validate_results()`를 독립 함수로 분리해 smoke_test에서 LLM 없이 테스트 가능
3. **evidence_quote 원문 대조**: LLM이 요약·변형한 인용구를 실제 회의록 원문과 대조해 hallucination 감지
4. **결정적 규칙 병행**: confidence/deadline 불일치 같은 논리적 모순은 LLM에 맡기지 않고 코드 레벨에서 감지

### Tradeoffs
| 결정 | 장점 | 단점 |
|------|------|------|
| 단일 파일 | 환경 구성 단순, 전체 흐름 한 파일 리뷰 가능, 검증 함수 분리로 LLM 없이 테스트 가능 | 파일이 길어짐. 프로덕션이었다면 모듈 분리 필요 |
| evidence_quote 원문 대조 | Hallucination 감지 | 공백·줄바꿈 차이로 false positive 가능 |
| JSON 전체를 한 번에 요청 | API 호출 1회 | 회의록이 매우 길면 토큰 초과 가능 |
| gemini-2.5-flash | 품질/비용 균형, 무료 티어 제공 | pro 대비 복잡한 추론 약할 수 있음 |
| confidence_reason 필드 추가 | LLM 판단 근거 투명화, 검토 용이 | evidence_quote와 달리 원문 대조로 검증 불가 — 틀린 이유를 그럴듯하게 반환해도 잡을 수 없음 |

---

## AI Tools Used and Verification

### AI coding tools used
- **Claude (claude.ai)**: 전체 코드 구조 설계, 프롬프트 초안 작성, smoke_test 작성에 활용

### Runtime LLM integration used by the service
- **Google Gemini API** (`gemini-2.5-flash`) — `google-genai` Python SDK 사용
- 설정 방법:
  ```bash
  pip install -r requirements.txt
  export GEMINI_API_KEY="AIza..."
  python extractor.py
  ```
- API 키 발급: https://aistudio.google.com/app/apikey (무료 티어 있음)

### How I verified AI/LLM output
1. **스키마 검증**: 필수 필드 존재 여부, confidence 허용 값 체크
2. **evidence_quote 원문 대조**: 공백 정규화 후 회의록 원문에 포함되는지 확인
3. **논리 일관성 체크**: `deadline=unknown + confidence=high` 조합 경고
4. **최소 수량 체크**: 액션 아이템 4개, 보류 3개, 미해결 1개 이상
5. **수동 리뷰**: 실제 출력 결과를 회의록과 직접 대조

---

## Testing Report

### Commands or smoke checks run
```bash
python smoke_test.py
```

### Results
```
결과: 10/10 통과  |  실패: 0개
```

테스트 항목:
- ✅ 정상 아이템 이슈 없음
- ✅ deadline 누락 감지
- ✅ 잘못된 confidence 감지
- ✅ 근거 없는 evidence_quote 감지
- ✅ deadline=unknown+confidence=high 경고
- ✅ 정상 JSON 파싱 성공
- ✅ 마크다운 코드블록 제거 후 파싱
- ✅ action_items >= 4
- ✅ deferred_items >= 3
- ✅ open_questions >= 1

### Bugs found and fixed
- LLM이 응답을 마크다운 코드블록(` ```json `)으로 감싸는 경우 → regex로 제거하는 전처리 추가
- evidence_quote 대조 시 줄바꿈·공백 차이로 false positive 발생 → `re.sub(r"\s+", " ", ...)` 정규화 적용
- LLM이 JSON 문자열 필드 중간에 줄바꿈을 삽입해 파싱 실패 → 프롬프트 규칙 추가 + `while` 루프 전처리로 이중 방어
- `setup_logger()` 중복 호출로 로그가 2~3회씩 중복 기록 → 핸들러 존재 여부 체크(`if logger.handlers`) 추가

### Untested areas
- 매우 긴 회의록 (토큰 초과 시나리오)
- 복수의 회의록 배치 처리
- 네트워크 타임아웃 재시도 로직
- evidence_quote에 특수문자/이모지 포함된 경우

---

## Final Status

- **Working**: CLI 실행, LLM 추출, 스키마 검증, evidence_quote 원문 대조, 최소 수량 체크, JSON export (스트레치 13번), confidence_reason 표시 (스트레치 12번), 실행 로그 적재 (`logs/`), smoke_test 10/10
- **Partially working**: evidence_quote 대조 — 공백 정규화로 대부분 처리되나 완전히 다른 문장이 부분 일치할 가능성 존재
- **Not working**: 없음 (필수 범위 내 전체 동작)

## Next Steps
1. 담당자별 액션 아이템 그룹화 출력 (`--group-by-owner`)
2. 매우 긴 회의록을 위한 청크 분할 처리
3. LLM 결과와 deterministic rule 결과 비교 리포트
4. 네트워크 타임아웃 재시도 로직 추가
