"""
smoke_test.py — 검증 레이어 및 파서 단위 테스트
LLM을 호출하지 않고, 로컬에서 실행 가능한 smoke check입니다.
"""

import json
import sys
import re

# extractor 모듈에서 검증 함수 임포트
sys.path.insert(0, ".")
from extractor import (
    validate_action_item,
    validate_results,
    parse_llm_output,
    REQUIRED_ACTION_FIELDS,
    VALID_CONFIDENCE,
)

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []


def check(name: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    results.append((name, condition, detail))
    icon = "✅" if condition else "❌"
    msg = f"  {icon} {name}"
    if detail:
        msg += f"\n     → {detail}"
    print(msg)


print("\n" + "═" * 55)
print("  🧪 Smoke Test — 검증 레이어")
print("═" * 55 + "\n")


# ── Test 1: 정상 액션 아이템 검증 통과 ──
print("[Test 1] 정상 액션 아이템 → 검증 통과")
SAMPLE_TRANSCRIPT = "준호: 금요일 오전까지 백엔드 필터 PR을 올리겠습니다."

good_item = {
    "owner": "준호",
    "task": "백엔드 필터 PR 올리기",
    "deadline": "금요일 오전",
    "confidence": "high",
    "evidence_quote": "금요일 오전까지 백엔드 필터 PR을 올리겠습니다.",
}
issues = validate_action_item(good_item, SAMPLE_TRANSCRIPT)
check("정상 아이템 이슈 없음", len(issues) == 0, str(issues) if issues else "")


# ── Test 2: 필수 필드 누락 감지 ──
print("\n[Test 2] 필수 필드 누락 → 감지")
bad_item_missing_field = {
    "owner": "준호",
    "task": "PR 올리기",
    # deadline 누락
    "confidence": "high",
    "evidence_quote": "금요일 오전까지 백엔드 필터 PR을 올리겠습니다.",
}
issues = validate_action_item(bad_item_missing_field, SAMPLE_TRANSCRIPT)
check("deadline 누락 감지", any("deadline" in i for i in issues), str(issues))


# ── Test 3: 잘못된 confidence 값 감지 ──
print("\n[Test 3] 잘못된 confidence 값 → 감지")
bad_confidence = {
    "owner": "준호",
    "task": "PR 올리기",
    "deadline": "금요일",
    "confidence": "very_high",   # 잘못된 값
    "evidence_quote": "금요일 오전까지 백엔드 필터 PR을 올리겠습니다.",
}
issues = validate_action_item(bad_confidence, SAMPLE_TRANSCRIPT)
check("잘못된 confidence 감지", any("confidence" in i for i in issues), str(issues))


# ── Test 4: evidence_quote가 회의록에 없는 경우 감지 ──
print("\n[Test 4] 근거 문장이 회의록에 없음 → 감지")
fabricated_quote = {
    "owner": "준호",
    "task": "PR 올리기",
    "deadline": "금요일",
    "confidence": "high",
    "evidence_quote": "이건 회의록에 없는 완전히 새로 만들어진 문장입니다.",
}
issues = validate_action_item(fabricated_quote, SAMPLE_TRANSCRIPT)
check("근거 없는 evidence_quote 감지", any("evidence_quote" in i or "원문" in i for i in issues), str(issues))


# ── Test 5: deadline=unknown 인데 confidence=high → 경고 ──
print("\n[Test 5] deadline=unknown + confidence=high → 경고")
inconsistent_item = {
    "owner": "준호",
    "task": "PR 올리기",
    "deadline": "unknown",
    "confidence": "high",
    "evidence_quote": "금요일 오전까지 백엔드 필터 PR을 올리겠습니다.",
}
issues = validate_action_item(inconsistent_item, SAMPLE_TRANSCRIPT)
check("deadline=unknown+confidence=high 경고", any("unknown" in i for i in issues), str(issues))


# ── Test 6: JSON 파싱 — 정상 JSON ──
print("\n[Test 6] 정상 JSON 파싱")
valid_json = json.dumps({"action_items": [], "deferred_items": [], "open_questions": []})
try:
    parsed = parse_llm_output(valid_json)
    check("정상 JSON 파싱 성공", isinstance(parsed, dict))
except SystemExit:
    check("정상 JSON 파싱 성공", False, "SystemExit 발생")


# ── Test 7: JSON 파싱 — 마크다운 코드블록 포함된 경우 ──
print("\n[Test 7] 마크다운 코드블록 포함된 JSON 파싱")
markdown_json = "```json\n" + json.dumps({"action_items": [], "deferred_items": [], "open_questions": []}) + "\n```"
try:
    parsed = parse_llm_output(markdown_json)
    check("마크다운 코드블록 제거 후 파싱", isinstance(parsed, dict))
except SystemExit:
    check("마크다운 코드블록 제거 후 파싱", False, "SystemExit 발생")


# ── Test 8: 최소 수량 검증 ──
print("\n[Test 8] 최소 수량 기준 검증")

TRANSCRIPT_MULTI = """
준호: 금요일 오전까지 백엔드 필터 PR을 올리겠습니다.
서연: 목요일 오후까지 검색창과 결과 리스트를 붙이겠습니다.
해린: 고객 안내 문구 초안을 작성하겠습니다. 마감은 금요일 점심 전까지로 하겠습니다.
도윤: 다음 스프린트 후보 목록에 동의어 검색, 익명화된 검색 로그, CS 모드, 금액 범위 검색을 적어두겠습니다.
"""

mock_data_pass = {
    "action_items": [
        {"owner": "준호", "task": "백엔드 필터 PR", "deadline": "금요일 오전", "confidence": "high",
         "evidence_quote": "금요일 오전까지 백엔드 필터 PR을 올리겠습니다."},
        {"owner": "서연", "task": "프론트 화면 붙이기", "deadline": "목요일 오후", "confidence": "high",
         "evidence_quote": "목요일 오후까지 검색창과 결과 리스트를 붙이겠습니다."},
        {"owner": "해린", "task": "고객 안내 문구 초안", "deadline": "금요일 점심 전", "confidence": "high",
         "evidence_quote": "마감은 금요일 점심 전까지로 하겠습니다."},
        {"owner": "도윤", "task": "다음 스프린트 후보 목록 이슈 등록", "deadline": "오늘", "confidence": "medium",
         "evidence_quote": "다음 스프린트 후보 목록에 동의어 검색, 익명화된 검색 로그, CS 모드, 금액 범위 검색을 적어두겠습니다."},
    ],
    "deferred_items": [
        {"item": "금액 범위 검색", "reason": "베타 제외", "evidence_quote": "금액 범위 검색은 이번 베타에서 제외합니다."},
        {"item": "동의어 검색", "reason": "베타 제외", "evidence_quote": "동의어 검색, CS 모드, 검색 로그도 이번에는 제외입니다."},
        {"item": "CS 모드", "reason": "범위 초과", "evidence_quote": "내부 CS 모드는 권한도 들어가고 범위가 커집니다."},
    ],
    "open_questions": [
        {"question": "날짜 검색 입력 형식 미결정", "raised_by": "서연",
         "evidence_quote": "날짜 검색 입력 형식을 YYYY-MM-DD로 할지, 달력 컴포넌트를 쓸지는 정해야 합니다."},
    ],
}

validation = validate_results(mock_data_pass, TRANSCRIPT_MULTI)
checks = validation["minimum_checks"]
check("action_items >= 4", checks["action_items_>=4"])
check("deferred_items >= 3", checks["deferred_items_>=3"])
check("open_questions >= 1", checks["open_questions_>=1"])


# ── 결과 요약 ──
print("\n" + "═" * 55)
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed
print(f"  결과: {passed}/{total} 통과  |  실패: {failed}개")
print("═" * 55 + "\n")

if failed > 0:
    sys.exit(1)
