"""GPU 없이도 experiment 쪽 계약을 검사할 수 있게 하는 가짜 experiment 루트.

CI에는 학습된 자(기준 모델)가 없어서 5건이 건너뛰어졌고, 더 큰 문제는 **제품의
핵심 경로가 한 번도 안 탔다**는 것이었다 — 업로드한 데이터셋에 대해 진단
서브프로세스를 돌리고 그 결과 JSON을 응답으로 바꾸는 길.

여기서 두 층을 흉내 낸다.

**경로 층.** `_weights_exist`는 파일이 있는지만 본다. 그러니 올바른 자리에
빈 `best.pt`를 놓으면 경로 규칙(`runs`/`runs_mc`/`runs_mc_coco` 접미사)과
프로파일 해석을 진짜로 검사할 수 있다. 자가 진짜일 필요가 없는 검사들이다.

**서브프로세스 층.** `EXPERIMENT_PYTHON`을 지금 돌고 있는 파이썬으로,
스크립트를 torch 없는 가짜로 바꾼다. 그러면 인자·cwd·환경변수·리턴코드·
타임아웃과 결과 JSON을 응답 모델로 바꾸는 부분까지 실제로 탄다.

**흉내 내지 않는 것: 추론 자체.** 그건 GPU가 필요하고 CI에서 못 한다.
여기서 보는 것은 "배선이 맞는가"지 "진단이 맞는가"가 아니다.
"""
import json
import sys
from pathlib import Path

# 실제 프로파일이 갖는 키. 모양이 달라지면 여기도 같이 틀어져야 한다.
PROFILE_MC = {
    "classes": ["Car", "Van", "Pedestrian", "Cyclist"],
    "present": {"missing": 0.88, "width": 0.42},
    "noise": {"missing": 0.22},
    "class_vulnerability": {},
}

# 진단 스크립트가 쓰는 결과 파일의 최소 모양. backend가 이걸 읽어
# LabelDiagnosisResult로 바꾼다 — 여기 키가 하나 빠지면 제품이 깨진다.
def diagnosis_payload(dataset_id: str) -> dict:
    return {
        "dataset": dataset_id,
        "generated_at": "2026-09-05T00:00:00+00:00",
        "summary": {
            "total_labels": 10,
            "total_findings": 2,
            "suspicion_ratio": 0.2,
            "dominant_type": "width",
            "dominant_ratio": 0.5,
            "systematic": False,
            "by_type": [
                {"suspicion": "width", "count": 1, "ratio": 0.5},
                {"suspicion": "missing", "count": 1, "ratio": 0.5},
            ],
            "ruler_fit": {
                "matched_labels": 8, "total_labels": 10,
                "matched_label_ratio": 0.8, "median_confidence": 0.77,
            },
        },
        "review_queue": [
            {"rank": 1, "image": "a.png", "label_index": 0, "suspicion": "width",
             "severity": 0.9, "detail": "예측보다 28% 작습니다",
             "box": [10.0, 20.0, 110.0, 220.0]},
            {"rank": 2, "image": "a.png", "label_index": None, "suspicion": "missing",
             "severity": 0.7, "detail": "확신 있는 예측이 있는데 라벨이 없습니다",
             "box": None},
        ],
        "caveat": "기준 모델의 예측과 라벨을 대조한 결과입니다.",
    }


# 가짜 진단 스크립트. 진짜와 같은 인자(--upload-id)를 받고, 같은 자리에
# 같은 이름으로 결과를 쓴다. 받은 환경변수는 따로 남겨 검사할 수 있게 한다.
STUB_SCRIPT = '''
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
if "--upload-id" not in args:
    sys.stderr.write("--upload-id 없음\\n")
    sys.exit(2)
dataset_id = args[args.index("--upload-id") + 1]

uploads = Path(os.environ["FAKE_UPLOADS_DIR"])
out = uploads / dataset_id
out.mkdir(parents=True, exist_ok=True)

# 받은 것을 그대로 남긴다 — backend가 무엇을 넘겼는지 검사에서 본다
(out / "stub_call.json").write_text(json.dumps({
    "argv": args,
    "cwd": os.getcwd(),
    "profile": os.environ.get("AIDA_RELIABILITY_PROFILE"),
    "classes": os.environ.get("AIDA_CLASSES"),
    "dataset": os.environ.get("AIDA_DATASET"),
}, ensure_ascii=False), encoding="utf-8")

payload = json.loads(os.environ["FAKE_DIAGNOSIS_JSON"])
payload["dataset"] = dataset_id
(out / "label_diagnosis.json").write_text(
    json.dumps(payload, ensure_ascii=False), encoding="utf-8")

if os.environ.get("FAKE_FAIL"):
    sys.stderr.write("일부러 낸 실패\\n")
    sys.exit(1)
if os.environ.get("FAKE_HANG"):
    import time
    time.sleep(30)
'''


def build(root: Path, uploads: Path, *, runs=("runs", "runs_mc")) -> Path:
    """가짜 experiment 루트를 만든다. EXPERIMENT_ROOT로 쓰면 된다."""
    root.mkdir(parents=True, exist_ok=True)

    # 자 자리표시자. _weights_exist는 있는지만 보므로 내용은 상관없다.
    for name in runs:
        w = root / name / "clean" / "weights"
        w.mkdir(parents=True, exist_ok=True)
        (w / "best.pt").write_bytes(b"not-a-real-checkpoint")

    (root / "reliability_profile_mc.json").write_text(
        json.dumps(PROFILE_MC, ensure_ascii=False), encoding="utf-8")

    (root / "diagnose_labels.py").write_text(STUB_SCRIPT, encoding="utf-8")
    (root / "diagnose_upload.py").write_text(STUB_SCRIPT, encoding="utf-8")
    return root


def python_path() -> Path:
    """EXPERIMENT_PYTHON 자리에 쓸 파이썬. 지금 돌고 있는 것을 그대로 쓴다."""
    return Path(sys.executable)
