"""외부 AI 블라인드 재심사 (계획: external_judges_plan.md).

API 키는 사용자 터미널에서만 넣는다. 예 (PowerShell):
  $env:OPENAI_API_KEY = "sk-..."      # 이 창에서만 유지된다
  $env:GEMINI_API_KEY = "..."
  python run_external_judges.py openai gpt-5
  python run_external_judges.py gemini gemini-2.5-pro
모델 ID는 실행 시점에 각 회사 문서에서 가장 강한 일반 모델로 고른다(위는 예시).
결과: results_v1/judge_ext_<공급사>.json (원문 응답, 모델 ID, 시각 포함). 같은 공급사는 한 번만 돌린다.
"""
import datetime
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results_v1")


def build_prompt():
    brief = open(os.path.join(RES, "JUDGE_BRIEF.md"), encoding="utf-8").read()
    key = json.load(open(os.path.join(RES, "blind_key.json"), encoding="utf-8"))
    parts = [brief, "\n\n아래가 원고다. JSON만 출력하라.\n"]
    for task in ("T1", "T2", "T3"):
        for slot in ("X", "Y"):
            text = open(os.path.join(RES, f"{task}_{key[task][slot]}.md"), encoding="utf-8").read()
            parts.append(f"\n===== {task} {slot} =====\n{text.strip()}\n")
    return "".join(parts)


def post(url, headers, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def ask_openai(model, prompt):
    data = post("https://api.openai.com/v1/chat/completions",
                {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                {"model": model, "messages": [{"role": "user", "content": prompt}]})
    return data["choices"][0]["message"]["content"], data.get("model", model)


def ask_gemini(model, prompt):
    data = post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                {"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                {"contents": [{"parts": [{"text": prompt}]}]})
    text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    return text, data.get("modelVersion", model)


def parse(text):
    s, e = text.find("{"), text.rfind("}")
    try:
        return json.loads(text[s:e + 1])
    except ValueError:
        return None


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("openai", "gemini"):
        sys.exit("사용법: python run_external_judges.py openai|gemini <모델ID>")
    sys.stdout.reconfigure(encoding="utf-8")
    vendor, model = sys.argv[1], sys.argv[2]
    out = os.path.join(RES, f"judge_ext_{vendor}.json")
    if os.path.exists(out):
        sys.exit(f"이미 있음: {out} — 계획상 한 번만 돌린다(L8).")
    text, model_id = (ask_openai if vendor == "openai" else ask_gemini)(model, build_prompt())
    parsed = parse(text)
    key = json.load(open(os.path.join(RES, "blind_key.json"), encoding="utf-8"))
    picks = {}
    if parsed:
        for task in ("T1", "T2", "T3"):
            pick = (parsed.get(task) or {}).get("pick")
            picks[task] = key[task].get(pick, "무효")
    record = {"vendor": vendor, "model": model_id, "time": datetime.datetime.now().isoformat(timespec="seconds"),
              "raw": text, "parsed": parsed, "picks_unblinded": picks}
    json.dump(record, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"저장: {out}\n모델: {model_id}\n고른 쪽(A=매뉴얼 없음, B=매뉴얼): {picks or '파싱 실패'}")


if __name__ == "__main__":
    main()
