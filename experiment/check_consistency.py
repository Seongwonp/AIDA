"""실험 산출물 정합성 검사 — 오류 없이 조용히 틀리는 것들을 잡는다.

이 프로젝트에서 반복해서 나온 사고들이 있다. 전부 예외를 던지지 않고 조용히
틀린 결과를 만들었다:

1. **이미지/라벨 개수 불일치** — data/processed/images/는 구성 간 공유이고
   data_loader를 돌릴 때마다 쌓인다. 조건 폴더가 그걸 통째로 링크하면 라벨
   없는 이미지가 "객체 없는 배경"으로 학습된다. cyclist_rich 실험이 이걸로
   통째로 무효가 됐다(docs/21 S).
2. **하드코딩된 조건 목록** — 새 조건군을 추가하면 by_name 조회에서 빠져
   KeyError가 나거나(run_all), 정렬 키가 NaN이 되거나(append_metrics),
   정리 대상에서 통째로 누락된다(cleanup_runs, 880MB).
3. **접미사 없는 경로** — 클래스 구성·시드·자가 달라도 같은 파일에 쓰면
   앞 결과를 덮는다. metrics_multi_seed.csv가 그럴 뻔했다.
4. **링크 아닌 이미지** — git이 심볼릭 링크를 경로 문자열이 담긴 74바이트
   텍스트로 복원한 적이 있다(Windows, core.symlinks 꺼짐). ultralytics는
   이걸 "corrupt image"로 조용히 건너뛰므로, 학습이 거의 빈 데이터셋으로
   돌아가면서도 끝까지 성공한다.

사용법:
  python check_consistency.py
  AIDA_CLASSES="Car,Van,Pedestrian,Cyclist" python check_consistency.py
"""
import sys
from pathlib import Path

import config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

problems: list[str] = []   # 결과를 망치는 것
warnings: list[str] = []   # 무해하지만 어수선한 것
notes: list[str] = []


def check_image_label_counts() -> None:
    """조건 폴더마다 이미지 수 == 라벨 수인가."""
    roots = [d for d in config.EXPERIMENT_ROOT.glob("conditions*") if d.is_dir()]
    checked = 0
    for root in roots:
        for cond in sorted(root.iterdir()):
            if not cond.is_dir():
                continue
            for split in ("train", "val"):
                imgs, lbls = cond / "images" / split, cond / "labels" / split
                if not imgs.is_dir() or not lbls.is_dir():
                    continue
                istems = {f.stem for f in imgs.iterdir()}
                lstems = {f.stem for f in lbls.iterdir()}
                checked += 1
                # 방향이 중요하다. ultralytics는 이미지 목록으로 데이터셋을
                # 만들고 경로를 바꿔 라벨을 찾는다. 그래서:
                #   이미지에만 있음 → 라벨 없는 이미지가 "객체 없는 배경"으로
                #                     학습된다. 조용히 결과를 망친다.
                #   라벨에만 있음   → 쓰이지 않고 무시된다. 무해.
                if istems - lstems:
                    problems.append(
                        f"라벨 없는 이미지: {root.name}/{cond.name}/{split} "
                        f"{len(istems - lstems)}장 — 배경으로 학습된다")
                if lstems - istems:
                    warnings.append(
                        f"이미지 없는 라벨: {root.name}/{cond.name}/{split} "
                        f"{len(lstems - istems)}개 — 무시되므로 무해")
    notes.append(f"조건 폴더 {checked}개 분할의 이미지/라벨 개수 확인")


def check_images_readable() -> None:
    """조건 폴더의 이미지가 진짜 이미지인가.

    git이 심볼릭 링크를 텍스트 파일로 복원해버리면 크기가 100바이트 미만이
    된다. 진짜 PNG는 KITTI 기준 수백 KB다. 매직 바이트까지 보면 확실하지만
    15만 장을 여는 건 느리므로 크기로 먼저 거른다.
    """
    checked = 0
    by_root: dict[str, int] = {}
    for root in config.EXPERIMENT_ROOT.glob("conditions*"):
        if not root.is_dir():
            continue
        for img in root.rglob("images/*/*.png"):
            checked += 1
            if img.stat().st_size < 1000:
                by_root[root.name] = by_root.get(root.name, 0) + 1
    for name, n in sorted(by_root.items()):
        problems.append(f"이미지가 아닌 파일: {name} {n}장 — 학습에서 조용히 "
                        f"빠진다. error_injector.build_condition으로 다시 링크할 것")
    notes.append(f"조건 폴더 이미지 {checked}장이 전부 실제 파일")


def check_condition_lookups() -> None:
    """모든 조건군이 _BY_NAME으로 조회되는가."""
    groups = {
        "CONDITIONS": config.CONDITIONS,
        "CLASS_SWAP_CONDITIONS": config.CLASS_SWAP_CONDITIONS,
        "REVIEW_SIM_CONDITIONS": config.REVIEW_SIM_CONDITIONS,
        "REFINED_CONDITIONS": config.REFINED_CONDITIONS,
    }
    for name, group in groups.items():
        missing = [c.name for c in group if c.name not in config._BY_NAME]
        if missing:
            problems.append(f"{name}의 {len(missing)}개가 _BY_NAME에 없음: {missing[:3]}")
    notes.append(f"조건군 {len(groups)}개가 전부 이름으로 조회됨 "
                 f"(총 {len(config._BY_NAME)}개)")


def check_path_namespacing() -> None:
    """클래스 구성이 바뀌면 모든 산출물 경로가 갈리는가."""
    import importlib
    import os

    def paths() -> dict:
        m = importlib.reload(config)
        return {
            "CONDITIONS_DIR": m.CONDITIONS_DIR.name,
            "RUNS_DIR": m.RUNS_DIR.name,
            "DATA_YAML_DIR": m.DATA_YAML_DIR.name,
            "LABELS_GT": m.LABELS_GT_TRAIN_DIR.parent.name,
            "METRICS_CSV": m.METRICS_CSV.name,
            "MULTI_SEED_CSV": m.MULTI_SEED_CSV.name,
            "AGG_CSV": m.AGG_CSV.name,
        }

    original = os.environ.get("AIDA_CLASSES")
    try:
        os.environ["AIDA_CLASSES"] = "Car"
        single = paths()
        os.environ["AIDA_CLASSES"] = "Car,Van"
        multi = paths()
    finally:
        if original is None:
            os.environ.pop("AIDA_CLASSES", None)
        else:
            os.environ["AIDA_CLASSES"] = original
        importlib.reload(config)

    same = [k for k in single if single[k] == multi[k]]
    if same:
        problems.append(f"클래스 구성이 달라도 같은 경로를 쓰는 항목: {same} "
                        f"— 한쪽이 다른 쪽 결과를 덮는다")
    notes.append(f"산출물 경로 {len(single)}종이 클래스 구성별로 분리됨")


def check_weights_present() -> None:
    """metrics에 행이 있는데 가중치가 없는 조건 (또는 그 반대)."""
    import pandas as pd

    if not config.METRICS_CSV.exists():
        notes.append(f"{config.METRICS_CSV.name} 없음 — 학습 전이면 정상")
        return
    rows = set(pd.read_csv(config.METRICS_CSV)["condition"])
    have = {d.name for d in config.RUNS_DIR.iterdir()
            if d.is_dir() and (d / "weights" / "best.pt").exists()} \
        if config.RUNS_DIR.is_dir() else set()
    orphan = sorted(rows - have)
    if orphan:
        problems.append(f"지표는 있는데 가중치가 없는 조건 {len(orphan)}개: "
                        f"{orphan[:4]} — 재현이 안 된다")
    notes.append(f"{config.METRICS_CSV.name} {len(rows)}행 중 "
                 f"{len(rows & have)}개가 가중치를 갖고 있음")


def main() -> None:
    print(f"클래스 구성: {','.join(config.CLASS_NAMES)}"
          f"{' / 프레임 선택: ' + config.FRAME_SELECT if config.FRAME_SELECT != 'random' else ''}\n")
    for fn in (check_image_label_counts, check_images_readable,
               check_condition_lookups, check_path_namespacing,
               check_weights_present):
        try:
            fn()
        except Exception as e:                      # 검사기가 죽어서 침묵하면 안 된다
            problems.append(f"{fn.__name__} 검사 자체가 실패: {e!r}")

    for n in notes:
        print(f"  OK  {n}")
    if warnings:
        print()
        shown = set()
        for w in warnings:                      # 같은 원인이 반복되면 한 번만
            key = w.split("/")[0] + w.rsplit("/", 1)[-1]
            if key not in shown:
                shown.add(key)
                print(f"  --  {w}")
        if len(warnings) > len(shown):
            print(f"      (같은 유형 {len(warnings)}건 중 {len(shown)}건만 표시)")
    if problems:
        print()
        for p in problems:
            print(f"  !!  {p}")
        print(f"\n결과를 망치는 문제 {len(problems)}건")
        raise SystemExit(1)
    print("\n결과를 망치는 문제 없음"
          + (f" (무해한 경고 {len(warnings)}건)" if warnings else ""))


if __name__ == "__main__":
    main()
