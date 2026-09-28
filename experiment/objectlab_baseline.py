"""Cleanlab ObjectLab 기준선 — 상용 라벨 오류 탐지 도구와 같은 입력으로 낸 박스 단위 점수.

왜 있나. 다음 비교(Q-A)의 기준선이 `1 − label_iou` 하나뿐이면 "왜 상용 도구와는 안 견줬나"에
답이 없다. ObjectLab(cleanlab.object_detection)은 같은 예측·라벨을 받아 박스마다
"위치가 틀렸을 가능성"(badloc)·"클래스가 바뀌었을 가능성"(swap)·"라벨이 빠졌을
가능성"(overlooked)을 낸다. 여기서는 그 점수를 **바꾸지 않고** 진단 결과의 모집단 행에 붙인다.

- 기존 라벨 행: `objectlab_score` = min(badloc, swap). 1이 깨끗, 0이 의심. 예측이 없는
  라벨은 ObjectLab이 1.0(깨끗)으로 두므로 `all_label_iou`와 상위 구성이 다르다.
- 미매칭 예측 행: `objectlab_overlooked`. ObjectLab은 확신도가 자기 문턱 아래인 예측에
  NaN을 주는데, 그 예측은 **이 방법의 모집단에 없다**(값을 지어내지 않는다).

cleanlab의 문턱·alpha는 **기본값 그대로** 쓴다 — AIDA 상수에 맞추면 기준선이 아니다.
cleanlab이 없으면 아무것도 붙이지 않고 `available=False`를 돌려준다.
"""
from __future__ import annotations

import math


def build_inputs(images: list[dict], num_classes: int):
    """진단 루프가 모은 이미지별 (labels, label_classes, predictions, confidences, pred_classes)를
    cleanlab 형식으로. labels[i] = {"bboxes": (L,4), "labels": (L,)}, predictions[i] =
    클래스마다 (M_k,5) 배열(x1 y1 x2 y2 conf). 순수 함수라 cleanlab 없이 검사한다."""
    import numpy as np
    labels, preds = [], []
    for im in images:
        lb = np.asarray(im["labels"], dtype=float).reshape(-1, 4)
        lc = np.asarray(im.get("label_classes") or [0] * len(lb), dtype=int).reshape(-1)
        labels.append({"bboxes": lb, "labels": lc})
        pb = np.asarray(im["predictions"], dtype=float).reshape(-1, 4)
        pc = np.asarray(im.get("pred_classes") or [0] * len(pb), dtype=int).reshape(-1)
        conf = np.asarray(im["confidences"], dtype=float).reshape(-1)
        per_class = []
        for k in range(num_classes):
            sel = pc == k
            per_class.append(np.concatenate([pb[sel], conf[sel][:, None]], axis=1)
                             if sel.any() else np.zeros((0, 5)))
        preds.append(per_class)
    return labels, preds


def prediction_order(image: dict, num_classes: int) -> list[int]:
    """cleanlab이 이 이미지의 예측을 세는 **차례**를 원래 예측 번호로 돌려준다.

    cleanlab은 클래스별 배열을 그대로 이어붙여(`_separate_prediction_single_box`)
    번호를 매긴다. 그래서 예측이 클래스 순으로 정렬돼 있지 않으면 cleanlab의 i번째
    점수는 원래 i번째 예측의 것이 **아니다.** 클래스가 하나뿐이면 차례가 같아 티가
    안 나지만, 여러 클래스에서는 남의 상자에 점수가 붙는다.
    """
    pc = image.get("pred_classes") or [0] * len(image["predictions"])
    return [j for k in range(num_classes) for j, c in enumerate(pc) if int(c) == k]


def score(images: list[dict], num_classes: int) -> dict:
    """이미지별 점수. cleanlab이 없으면 {"available": False}."""
    try:
        import cleanlab
        from cleanlab.object_detection import rank
    except ImportError as exc:
        return {"available": False, "reason": f"cleanlab 없음: {exc}"}
    labels, preds = build_inputs(images, num_classes)
    badloc = rank.compute_badloc_box_scores(labels=labels, predictions=preds)
    swap = rank.compute_swap_box_scores(labels=labels, predictions=preds)
    overlooked = rank.compute_overlooked_box_scores(labels=labels, predictions=preds)
    label_scores: dict[tuple[str, int], float] = {}
    pred_scores: dict[tuple[str, int], float] = {}
    for im, b, s, o in zip(images, badloc, swap, overlooked):
        for i in range(len(im["labels"])):
            label_scores[(im["image"], i)] = round(float(min(b[i], s[i])), 4)
        # cleanlab 차례(i) → 원래 예측 번호(j). 클래스가 여럿이면 둘이 다르다.
        for i, j in enumerate(prediction_order(im, num_classes)):
            v = float(o[i]) if i < len(o) else float("nan")
            if not math.isnan(v):
                pred_scores[(im["image"], j)] = round(v, 4)
    return {"available": True, "cleanlab_version": cleanlab.__version__,
            "label_scores": label_scores, "pred_scores": pred_scores,
            "settings": "cleanlab 기본값 (alpha·문턱 미변경)"}


def attach(population: dict, images: list[dict], scored: dict) -> dict:
    """모집단 행에 점수를 붙인다. 행은 (image, label_index) / (image, 예측 상자)로 잇는다."""
    meta = {"available": scored.get("available", False)}
    for k in ("cleanlab_version", "reason", "settings"):
        if k in scored:
            meta[k] = scored[k]
    if not scored.get("available"):
        return meta
    for row in population.get("all_labels", []):
        v = scored["label_scores"].get((row["image"], row["label_index"]))
        if v is not None:
            row["objectlab_score"] = v
    box_index = {}
    for im in images:
        for j, box in enumerate(im["predictions"]):
            box_index[(im["image"], tuple(round(float(x), 1) for x in box))] = j
    attached = 0
    for row in population.get("unmatched_predictions", []):
        j = box_index.get((row["image"], tuple(row["box"])))
        v = scored["pred_scores"].get((row["image"], j)) if j is not None else None
        if v is not None:
            row["objectlab_overlooked"] = v
            attached += 1
    meta["labels_scored"] = sum("objectlab_score" in r for r in population.get("all_labels", []))
    meta["predictions_scored"] = attached
    return meta
