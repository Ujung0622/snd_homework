"""
Meeting Action Item Extractor
한국어 회의록 → 액션 아이템 / 보류 항목 / 미해결 질문 추출기
"""

import os
import sys
import json
import logging
import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

# .env 파일 자동 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv 없으면 환경변수에서 직접 읽음

try:
    from google import genai
    from google.genai import errors as genai_errors
except ImportError:
    print("[ERROR] google-genai 패키지가 설치되지 않았습니다. 'pip install google-genai' 를 실행하세요.")
    sys.exit(1)


# ─────────────────────────────────────────────
# 스키마 정의
# ─────────────────────────────────────────────

REQUIRED_ACTION_FIELDS = {"owner", "task", "deadline", "confidence", "evidence_quote"}
VALID_CONFIDENCE = {"high", "medium", "low"}


# ─────────────────────────────────────────────
# 로거 설정
# ─────────────────────────────────────────────

def setup_logger() -> logging.Logger:
    """logs/ 폴더에 날짜별 로그 파일을 생성합니다."""
    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    log_filename = logs_dir / f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

    logger = logging.getLogger("extractor")
    logger.setLevel(logging.DEBUG)

    # 파일 핸들러 (logs/ 폴더)
    fh = logging.FileHandler(log_filename, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # 콘솔 핸들러 (터미널 — INFO 이상만)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.debug(f"로그 파일 생성: {log_filename}")
    return logger


logger = setup_logger() if __name__ == "__main__" else logging.getLogger("extractor")


# ─────────────────────────────────────────────
# LLM 프롬프트
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """당신은 한국어 회의록에서 액션 아이템을 정확하게 추출하는 전문 분석가입니다.

반드시 아래 규칙을 따르세요:
1. 회의록에 명시적으로 나온 내용만 추출합니다. 추측하지 않습니다.
2. 담당자(owner)가 회의록에 없으면 반드시 "unknown"으로 표시합니다.
3. 마감일(deadline)이 회의록에 없으면 반드시 "unknown"으로 표시합니다.
4. evidence_quote는 회의록 원문에서 그대로 가져온 문장이어야 합니다. 요약하거나 변형하지 마세요.
5. confidence는 아래 기준으로 산정합니다:
   - high: 담당자, 할 일, 마감일 모두 명확히 언급됨
   - medium: 담당자 또는 마감일 중 하나가 불명확함
   - low: 담당자와 마감일 모두 불명확하거나 발언이 모호함
6. confidence_reason은 왜 그 confidence 값을 산정했는지 한 문장으로 설명합니다. 예: "담당자(준호)와 마감일(금요일 오전) 모두 명확히 언급됨"
7. open_questions는 회의록에서 끝까지 결론이 나지 않은 질문만 포함합니다. 누군가 명확한 답변("아니요", "하지 않습니다", "제외합니다", "결정됐습니다" 등)을 했다면 open_questions에 포함하지 마세요.
8. JSON 외의 텍스트는 절대 출력하지 마세요.
"""

EXTRACTION_PROMPT_TEMPLATE = """아래 회의록을 분석해서 JSON 형식으로 결과를 반환하세요.

---회의록 시작---
{transcript}
---회의록 끝---

반환 형식 (JSON만, 마크다운 코드블록 없이):
{{
  "action_items": [
    {{
      "owner": "담당자 이름 또는 unknown",
      "task": "구체적인 할 일",
      "deadline": "마감일 또는 unknown",
      "confidence": "high | medium | low",
      "confidence_reason": "confidence 산정 이유 한 문장",
      "evidence_quote": "회의록 원문 그대로",
      "notes": "선택적 보충 설명"
    }}
  ],
  "deferred_items": [
    {{
      "item": "보류/제외된 항목명",
      "reason": "왜 이번 범위에서 제외되었는지",
      "evidence_quote": "회의록 원문 그대로"
    }}
  ],
  "open_questions": [
    {{
      "question": "미해결 질문 또는 애매한 부분",
      "raised_by": "누가 제기했는지 또는 unknown",
      "evidence_quote": "회의록 원문 그대로"
    }}
  ]
}}
"""


# ─────────────────────────────────────────────
# LLM 호출
# ─────────────────────────────────────────────

def call_llm(transcript: str, api_key: str) -> str:
    """Google Gemini API를 호출해 회의록을 분석합니다."""
    client = genai.Client(api_key=api_key)

    prompt = SYSTEM_PROMPT + "\n\n" + EXTRACTION_PROMPT_TEMPLATE.format(transcript=transcript)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
    except genai_errors.APIError as e:
        status = getattr(e, "status_code", None)
        if status == 401 or status == 403:
            logger.error("API 키가 유효하지 않습니다. GEMINI_API_KEY를 확인하세요.")
        elif status == 429:
            logger.error("API 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.")
        else:
            logger.error(f"API 호출 실패: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"예상치 못한 오류: {e}")
        sys.exit(1)

    raw_text = response.text
    if not raw_text:
        logger.error("LLM이 빈 응답을 반환했습니다. (Safety filter 또는 빈 출력)")
        sys.exit(1)
    raw_text = raw_text.strip()
    logger.debug(f"LLM 응답 수신 완료 ({len(raw_text)}자)")
    return raw_text


# ─────────────────────────────────────────────
# 검증 레이어
# ─────────────────────────────────────────────

def parse_llm_output(raw_text: str) -> dict:
    logger.debug(f"raw_text: {raw_text}")
    """LLM 응답을 JSON으로 파싱합니다."""
    # 마크다운 코드블록 제거 (```json ... ``` 또는 ``` ... ```)
    cleaned = re.sub(r"```(?:json)?\s*", "", raw_text)
    cleaned = re.sub(r"```", "", cleaned).strip()
    try:
        logger.debug(f"cleaned: {cleaned}")
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"LLM 응답을 JSON으로 파싱할 수 없습니다: {e}")
        logger.debug(f"LLM 원문:\n{raw_text[:500]}")
        sys.exit(1)


def validate_action_item(item: dict, transcript: str) -> list[str]:
    """액션 아이템 하나를 검증하고, 문제 목록을 반환합니다."""
    issues = []
    logger.debug(f"item: {item}")

    # 필수 필드 존재 여부
    for field in REQUIRED_ACTION_FIELDS:
        if field not in item:
            issues.append(f"필수 필드 누락: '{field}'")

    # confidence 값 유효성
    conf = item.get("confidence", "")
    if conf not in VALID_CONFIDENCE:
        issues.append(f"confidence 값 비정상: '{conf}' (허용: {VALID_CONFIDENCE})")

    # evidence_quote 실제 포함 여부 (회의록에 있어야 함)
    quote = item.get("evidence_quote", "")
    if quote and len(quote) > 10:
        # 공백/줄바꿈 정규화 후 비교
        norm_transcript = re.sub(r"\s+", " ", transcript)
        norm_quote = re.sub(r"\s+", " ", quote)
        if norm_quote not in norm_transcript:
            issues.append(f"evidence_quote가 회의록 원문에서 찾을 수 없음: '{quote[:60]}...'")
    else:
        issues.append("evidence_quote가 너무 짧거나 비어 있음")

    # deadline이 unknown이면 confidence가 high가 아니어야 함
    if item.get("deadline") == "unknown" and item.get("confidence") == "high":
        issues.append("deadline이 unknown인데 confidence가 high — 재검토 필요")

    return issues


def validate_results(data: dict, transcript: str) -> dict:
    logger.debug(f"data: {data}")

    """전체 결과를 검증하고 플래그를 추가합니다."""
    action_items = data.get("action_items", [])
    deferred_items = data.get("deferred_items", [])
    open_questions = data.get("open_questions", [])

    validation_report = {
        "action_item_issues": [],
        "counts": {
            "action_items": len(action_items),
            "deferred_items": len(deferred_items),
            "open_questions": len(open_questions),
        },
        "minimum_checks": {},
    }

    # 각 액션 아이템 검증
    for i, item in enumerate(action_items):
        issues = validate_action_item(item, transcript)
        if issues:
            item["_validation_issues"] = issues
            validation_report["action_item_issues"].append({
                "index": i,
                "task": item.get("task", "(unknown)"),
                "issues": issues,
            })
        else:
            item["_validation_issues"] = []

    # 최소 수량 체크
    validation_report["minimum_checks"] = {
        "action_items_>=4": len(action_items) >= 4,
        "deferred_items_>=3": len(deferred_items) >= 3,
        "open_questions_>=1": len(open_questions) >= 1,
    }

    # open_questions 맥락 추적 검증
    validation_report["resolved_question_warnings"] = validate_open_questions(data, transcript)

    return validation_report


# 회의록에서 결론을 나타내는 패턴
RESOLUTION_PATTERNS = [
    r"아니요[,.]?\s",
    r"하지 않습니다",
    r"하지 않을",
    r"않기로",
    r"제외합니다",
    r"제외하기로",
    r"결정됐습니다",
    r"결정했습니다",
    r"결론은",
    r"하지 않는 게 좋",
    r"하지 않겠",
    r"빼는 게 맞",
    r"제한합시다",
    r"으로 합시다",
]


def check_question_resolved(question_quote: str, transcript: str) -> tuple[bool, str]:
    logger.debug(f"question_quote: {question_quote}")
    """
    open_question의 evidence_quote 이후 회의록에서 결론 패턴이 나오는지 확인합니다.
    Returns: (is_resolved, resolution_sentence)
    """
    norm_transcript = re.sub(r"\s+", " ", transcript)
    norm_quote = re.sub(r"\s+", " ", question_quote)

    # 질문 발언 위치 찾기
    quote_pos = norm_transcript.find(norm_quote)
    if quote_pos == -1:
        return False, ""

    # 질문 이후 텍스트만 검사
    after_quote = norm_transcript[quote_pos + len(norm_quote):]

    for pattern in RESOLUTION_PATTERNS:
        match = re.search(pattern, after_quote)
        if match:
            # 결론 문장 추출 (앞뒤 30자)
            start = max(0, match.start() - 30)
            end = min(len(after_quote), match.end() + 30)
            snippet = after_quote[start:end].strip()
            return True, f"...{snippet}..."

    return False, ""


def validate_open_questions(data: dict, transcript: str) -> list[dict]:
    logger.debug(f"data: {data}")
    """
    open_questions 중 회의록에서 이미 결론이 난 항목을 찾아 플래그를 붙입니다.
    """
    flagged = []
    for i, q in enumerate(data.get("open_questions", [])):
        quote = q.get("evidence_quote", "")
        if not quote:
            continue
        is_resolved, resolution = check_question_resolved(quote, transcript)
        if is_resolved:
            q["_resolved_warning"] = f"이미 결론 난 항목으로 보임 → \"{resolution}\""
            flagged.append({
                "index": i,
                "question": q.get("question", "")[:60],
                "resolution_hint": resolution,
            })
            logger.debug(f"open_question [{i}] 결론 난 항목 감지: {q.get('question', '')[:40]}")
    return flagged


# ─────────────────────────────────────────────
# 출력 포맷터
# ─────────────────────────────────────────────

CONFIDENCE_EMOJI = {"high": "🟢", "medium": "🟡", "low": "🔴"}


def print_results(data: dict, validation: dict, show_issues: bool = True):
    """분석 결과를 터미널에 보기 좋게 출력합니다."""

    sep = "─" * 60

    print(f"\n{'═' * 60}")
    print("  📋 회의록 액션 아이템 추출 결과")
    print(f"{'═' * 60}")

    # ── 액션 아이템 ──
    action_items = data.get("action_items", [])
    print(f"\n🎯 액션 아이템 ({len(action_items)}개)\n{sep}")

    for i, item in enumerate(action_items, 1):
        conf = item.get("confidence", "?")
        emoji = CONFIDENCE_EMOJI.get(conf, "⚪")
        issues = item.get("_validation_issues", [])
        flag = " ⚠️" if issues else ""

        print(f"\n[{i}] {item.get('task', '(없음)')}{flag}")
        print(f"  담당자  : {item.get('owner', 'unknown')}")
        print(f"  마감일  : {item.get('deadline', 'unknown')}")
        print(f"  신뢰도  : {emoji} {conf}")
        if item.get("confidence_reason"):
            print(f"  판단근거: {item.get('confidence_reason')}")
        print(f"  근거    : \"{item.get('evidence_quote', '')}\"")
        if item.get("notes"):
            print(f"  비고    : {item.get('notes')}")
        if show_issues and issues:
            for issue in issues:
                print(f"  ⚠️  검증 경고: {issue}")

    # ── 보류/제외 항목 ──
    deferred = data.get("deferred_items", [])
    print(f"\n\n🚫 보류/제외 항목 ({len(deferred)}개)\n{sep}")
    for i, item in enumerate(deferred, 1):
        print(f"\n[{i}] {item.get('item', '(없음)')}")
        print(f"  이유    : {item.get('reason', '')}")
        print(f"  근거    : \"{item.get('evidence_quote', '')}\"")

    # ── 미해결 질문 ──
    questions = data.get("open_questions", [])
    print(f"\n\n❓ 미해결 질문 / 애매한 부분 ({len(questions)}개)\n{sep}")
    for i, item in enumerate(questions, 1):
        warning = item.get("_resolved_warning", "")
        flag = " ⚠️ 이미 해결됨" if warning else ""
        print(f"\n[{i}] {item.get('question', '(없음)')}{flag}")
        print(f"  제기자  : {item.get('raised_by', 'unknown')}")
        print(f"  근거    : \"{item.get('evidence_quote', '')}\"")
        if warning:
            print(f"  ⚠️  {warning}")

    # ── 검증 리포트 ──
    print(f"\n\n🔍 검증 결과\n{sep}")
    checks = validation.get("minimum_checks", {})
    for check, passed in checks.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {check}")

    issue_list = validation.get("action_item_issues", [])
    if issue_list:
        print(f"\n\n⚠️  근거 약한 항목 / 검증 필요 ({len(issue_list)}개)\n{sep}")
        for v in issue_list:
            print(f"\n  [{v['index']+1}] {v['task'][:50]}")
            for iss in v["issues"]:
                print(f"       → {iss}")
    else:
        print("  ✅ 모든 액션 아이템 검증 통과")

    resolved_list = validation.get("resolved_question_warnings", [])
    if resolved_list:
        print(f"\n\n⚠️  이미 해결된 항목이 open_questions에 포함됨 ({len(resolved_list)}개)\n{sep}")
        for v in resolved_list:
            print(f"\n  [{v['index']+1}] {v['question']}")
            print(f"       → 결론 근거: \"{v['resolution_hint']}\"")
    else:
        print("  ✅ open_questions 맥락 검증 통과")

    print(f"\n{'═' * 60}\n")


def export_json(data: dict, output_path: str):
    """결과를 JSON 파일로 저장합니다."""
    # _validation_issues 필드 제거 후 저장
    clean_data = json.loads(json.dumps(data))
    for item in clean_data.get("action_items", []):
        item.pop("_validation_issues", None)
    for item in clean_data.get("open_questions", []):
        item.pop("_resolved_warning", None)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON 파일로 저장됨: {output_path}")


# ─────────────────────────────────────────────
# CLI 진입점
# ─────────────────────────────────────────────

def main():
    global logger
    logger = setup_logger()

    parser = argparse.ArgumentParser(
        description="한국어 회의록에서 액션 아이템을 추출합니다.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "transcript",
        nargs="?",
        default="meeting_transcript.md",
        help="회의록 파일 경로 (기본값: meeting_transcript.md)",
    )
    parser.add_argument(
        "--export-json",
        metavar="OUTPUT",
        help="결과를 JSON 파일로 저장 (예: --export-json result.json)",
    )
    parser.add_argument(
        "--no-validation-warnings",
        action="store_true",
        help="검증 경고를 출력하지 않음",
    )
    args = parser.parse_args()

    # API 키 확인
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        logger.error("  export GEMINI_API_KEY='AIza...'  또는  .env 파일을 설정하세요.")
        sys.exit(1)

    # 회의록 로드
    transcript_path = Path(args.transcript)
    if not transcript_path.exists():
        logger.error(f"파일을 찾을 수 없습니다: {transcript_path}")
        sys.exit(1)

    transcript = transcript_path.read_text(encoding="utf-8")
    logger.info(f"회의록 로드 완료: {transcript_path} ({len(transcript)}자)")

    # LLM 호출
    logger.info("LLM 분석 중... (수 초 소요)")
    raw_output = call_llm(transcript, api_key)

    # 파싱
    data = parse_llm_output(raw_output)
    logger.debug(f"파싱 완료 — 액션 아이템 {len(data.get('action_items', []))}개")

    # 검증
    validation = validate_results(data, transcript)
    issue_count = len(validation.get("action_item_issues", []))
    logger.debug(f"검증 완료 — 경고 {issue_count}개")

    # 출력
    print_results(data, validation, show_issues=not args.no_validation_warnings)

    # JSON export
    if args.export_json:
        export_json(data, args.export_json)

    # 최소 수량 미달 시 경고
    checks = validation.get("minimum_checks", {})
    if not all(checks.values()):
        logger.warning("일부 최소 수량 기준을 충족하지 못했습니다. 위 검증 결과를 확인하세요.")
        sys.exit(2)


if __name__ == "__main__":
    main()