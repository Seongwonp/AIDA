"""nuImages 키프레임을 AIDA가 읽는 YOLO 폴더(images/·labels/·classes.txt)로 바꾼다.

nuImages는 JSON 표(`v1.0-<split>/*.json`)와 이미지(`samples/`·`sweeps/`)로 온다. 공식 devkit을
설치하지 않고 표만 읽는다 — 실험 가상환경(torch·ultralytics)에 의존성을 더하지 않으려는 것이다.

**주석이 달린 키프레임만** 변환한다. sweep(앞뒤 프레임)에는 주석이 없다.

    ./venv/Scripts/python.exe nuimages_to_yolo.py --src D:/AIDA-eval/nuimages/mini \\
        --version v1.0-mini --out D:/AIDA-eval/nuimages/dev_mini_yolo \\
        --category vehicle.car=0 --class-names Car

**데이터 조건** (docs/evaluation-data.md "사용자 결정 — W1"): 비상업 연구·포트폴리오 용도, 원본
이미지·라벨을 저장소에 넣지 않는다. 출력 폴더는 저장소 밖에 둔다.
"""
import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

TABLES = ("category", "log", "sensor", "calibrated_sensor", "sample", "sample_data", "object_ann")


def load_tables(src_root: Path, version: str) -> dict[str, list[dict]]:
    root = Path(src_root) / version
    return {name: json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
            for name in TABLES}


def check_categories(tables: dict, mapping: dict[str, int]) -> None:
    """모르는 범주 이름을 거부한다 — 오타 하나로 조용히 0개가 변환되면 안 된다."""
    known = {c["name"] for c in tables["category"]}
    unknown = sorted(set(mapping) - known)
    if unknown:
        raise ValueError(f"nuImages에 없는 범주 이름: {', '.join(unknown)}")


def keyframes(tables: dict, cameras: set[str] | None = None) -> list[dict]:
    """주석이 달린 키프레임 한 장씩. 표에 적힌 순서를 그대로 쓴다."""
    samples = {s["token"]: s for s in tables["sample"]}
    logs = {log["token"]: log for log in tables["log"]}
    sensors = {s["token"]: s for s in tables["sensor"]}
    calibrated = {c["token"]: c for c in tables["calibrated_sensor"]}
    rows = []
    for d in tables["sample_data"]:
        if not d["is_key_frame"]:
            continue
        camera = sensors[calibrated[d["calibrated_sensor_token"]]["sensor_token"]]["channel"]
        if cameras is not None and camera not in cameras:
            continue
        sample = samples[d["sample_token"]]
        rows.append({
            "sample_data_token": d["token"],
            "sample_token": d["sample_token"],
            "log_token": sample["log_token"],
            "location": logs[sample["log_token"]].get("location"),
            "camera": camera,
            "filename": d["filename"],
            "width": d["width"],
            "height": d["height"],
        })
    return rows


def index_objects(tables: dict) -> dict[str, list[dict]]:
    by_sd: dict[str, list[dict]] = defaultdict(list)
    for o in tables["object_ann"]:
        by_sd[o["sample_data_token"]].append(o)
    return by_sd


def yolo_lines(tables: dict, sample_data_token: str, width: int, height: int,
               mapping: dict[str, int],
               objects_by_sd: dict[str, list[dict]] | None = None) -> tuple[list[str], dict]:
    """한 이미지의 YOLO 줄과, 무엇을 몇 개 버리거나 잘랐는지.

    상자는 이미지 경계로 **자르고 센다**(`clipped`). 자른 뒤 폭이나 높이가 0 이하이면 버리고
    센다(`degenerate`). 고르지 않은 범주는 `other_category`로 센다 — 조용히 사라지지 않게.
    """
    names = {c["token"]: c["name"] for c in tables["category"]}
    objects = (objects_by_sd if objects_by_sd is not None else index_objects(tables)).get(
        sample_data_token, [])
    report = {"kept": 0, "other_category": 0, "clipped": 0, "degenerate": 0}
    lines = []
    for o in objects:
        name = names[o["category_token"]]
        if name not in mapping:
            report["other_category"] += 1
            continue
        x1, y1, x2, y2 = (float(v) for v in o["bbox"])
        cx1, cy1 = min(max(x1, 0.0), width), min(max(y1, 0.0), height)
        cx2, cy2 = min(max(x2, 0.0), width), min(max(y2, 0.0), height)
        bw, bh = cx2 - cx1, cy2 - cy1
        if bw <= 0 or bh <= 0:
            report["degenerate"] += 1
            continue
        if (cx1, cy1, cx2, cy2) != (x1, y1, x2, y2):
            report["clipped"] += 1
        report["kept"] += 1
        lines.append(f"{mapping[name]} {(cx1 + bw / 2) / width:.6f} {(cy1 + bh / 2) / height:.6f} "
                     f"{bw / width:.6f} {bh / height:.6f}")
    return lines, report


def convert(src_root: Path, version: str, out_dir: Path, mapping: dict[str, int],
            class_names: list[str], cameras: set[str] | None = None,
            sample_data_tokens: set[str] | None = None) -> dict:
    """키프레임을 YOLO 폴더로 옮기고 출처 명세(`nuimages_manifest.json`)를 남긴다.

    **이미 있는 출력 폴더에는 쓰지 않는다** — 다른 변환 결과를 섞거나 덮어쓰지 않게.
    """
    out_dir = Path(out_dir)
    if (out_dir / "images").exists() or (out_dir / "labels").exists():
        raise FileExistsError(f"이미 변환 결과가 있다 — 덮어쓰지 않는다: {out_dir}")

    tables = load_tables(src_root, version)
    check_categories(tables, mapping)
    rows = keyframes(tables, cameras)
    if sample_data_tokens is not None:
        rows = [r for r in rows if r["sample_data_token"] in sample_data_tokens]
    objects = index_objects(tables)

    (out_dir / "images").mkdir(parents=True)
    (out_dir / "labels").mkdir(parents=True)
    totals = {"kept": 0, "other_category": 0, "clipped": 0, "degenerate": 0}
    seen: set[str] = set()
    manifest_rows = []
    for r in rows:
        image = Path(r["filename"]).name
        if image in seen:
            raise ValueError(f"이미지 이름이 겹친다: {image}")
        seen.add(image)
        shutil.copyfile(Path(src_root) / r["filename"], out_dir / "images" / image)
        lines, report = yolo_lines(tables, r["sample_data_token"], r["width"], r["height"],
                                   mapping, objects)
        (out_dir / "labels" / f"{Path(image).stem}.txt").write_text(
            "".join(line + "\n" for line in lines), encoding="utf-8")
        for key in totals:
            totals[key] += report[key]
        manifest_rows.append({"image": image, **{k: r[k] for k in (
            "sample_data_token", "sample_token", "log_token", "location", "camera",
            "width", "height")}, "labels": len(lines)})

    (out_dir / "classes.txt").write_text("".join(n + "\n" for n in class_names), encoding="utf-8")
    manifest = {
        "source": "nuImages",
        "version": version,
        "license_note": "CC BY-NC-SA 4.0 + nuScenes Terms of Use (non-commercial) — 원본을 재배포하지 않는다",
        "category_mapping": mapping,
        "class_names": class_names,
        "cameras": sorted(cameras) if cameras else None,
        "images": len(manifest_rows),
        "labels": len(manifest_rows),
        "report": totals,
        "rows": manifest_rows,
    }
    (out_dir / "nuimages_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # 이미지 → 주행 기록. 평가 묶음이 재표집 단위로 얼린다(backend `groups.json`). 이웃 프레임을
    # 독립 표본으로 세지 않게 한다.
    (out_dir / "groups.json").write_text(
        json.dumps({r["image"]: r["log_token"] for r in manifest_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="nuImages 키프레임 → YOLO 폴더")
    parser.add_argument("--src", required=True, help="nuImages를 푼 폴더 (v1.0-*/, samples/)")
    parser.add_argument("--version", required=True, help="예: v1.0-mini, v1.0-val")
    parser.add_argument("--out", required=True, help="출력 폴더 — 저장소 밖")
    parser.add_argument("--category", action="append", required=True,
                        help="범주=클래스번호, 예: vehicle.car=0 (여러 번)")
    parser.add_argument("--class-names", nargs="+", required=True)
    parser.add_argument("--cameras", nargs="*", help="예: CAM_FRONT (없으면 전부)")
    parser.add_argument("--tokens-file", help="변환할 sample_data 토큰 목록(한 줄에 하나)")
    args = parser.parse_args()

    mapping = {}
    for item in args.category:
        name, _, idx = item.partition("=")
        mapping[name] = int(idx)
    tokens = None
    if args.tokens_file:
        tokens = {t.strip() for t in Path(args.tokens_file).read_text(encoding="utf-8").splitlines()
                  if t.strip()}
    manifest = convert(Path(args.src), args.version, Path(args.out), mapping, args.class_names,
                       set(args.cameras) if args.cameras else None, tokens)
    print(json.dumps({k: manifest[k] for k in ("version", "images", "report", "cameras")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
