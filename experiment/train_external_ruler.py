"""외부 데이터의 YOLO 폴더로 자(기준 모델)를 학습한다 — nuImages용 (docs/nuimages-data-plan.md).

`train.py`는 오류 주입 조건 전용이라 외부 데이터 폴더를 못 받는다. 이 스크립트는 `nuimages_to_yolo.py`가
만든 폴더 둘(학습용·학습 검증용)을 받아 `yolov8n.pt`에서 미세조정한다.

    ./venv/Scripts/python.exe train_external_ruler.py \\
        --train D:/AIDA-eval/nuimages/yolo/ruler_train --val D:/AIDA-eval/nuimages/yolo/ruler_val \\
        --name car_v1

**학습 검증용에 적합도 확인용을 쓰지 않는다** — best.pt를 그걸로 고르면 확인 수치가 부풀려진다.

**가중치를 공개하지 않는다.** Ultralytics는 학습된 모델도 AGPL-3.0이라 하고, 학습 자료(nuImages)는
CC BY-NC-SA 4.0이다(docs/evaluation-data.md "사용자 결정 — W1").

학습 설정은 `config`(에폭·배치·입력 크기·씨앗)를 그대로 쓴다. 출력은 `runs_nuimages/<name>/`(git 제외)이고
**이미 있으면 덮어쓰지 않는다.**
"""
import argparse
import hashlib
import json
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parent
DEFAULT_PROJECT = EXPERIMENT / "runs_nuimages"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def check_folder(folder: Path) -> tuple[list[str], int]:
    """YOLO 폴더(images/·labels/·classes.txt)인가. (클래스 목록, 이미지 수)."""
    folder = Path(folder)
    for sub in ("images", "labels"):
        if not (folder / sub).is_dir():
            raise ValueError(f"{sub}/ 폴더가 없다: {folder}")
    classes_file = folder / "classes.txt"
    if not classes_file.exists():
        raise ValueError(f"classes.txt가 없다: {folder}")
    classes = [c.strip() for c in classes_file.read_text(encoding="utf-8").splitlines() if c.strip()]
    images = sum(1 for p in (folder / "images").iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if images == 0:
        raise ValueError(f"이미지가 없다: {folder}")
    return classes, images


def _listing_sha256(folder: Path) -> str:
    """이미지 이름 목록의 지문 — 어느 이미지로 학습했는지 대조용."""
    names = sorted(p.name for p in (Path(folder) / "images").iterdir())
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()


def prepare(train_dir: Path, val_dir: Path, project: Path, name: str, write: bool = True) -> dict:
    """학습 전에 막을 것을 막고 데이터 설정 파일을 쓴다. 학습은 하지 않는다.

    `write=False`(점검만)면 실행 폴더를 만들지 않는다 — 만들면 다음 실제 학습이 "이미 있다"로 막힌다.
    """
    train_classes, train_images = check_folder(train_dir)
    val_classes, val_images = check_folder(val_dir)
    if train_classes != val_classes:
        raise ValueError(f"학습·검증의 클래스 목록이 다르다: {train_classes} / {val_classes}")
    run_dir = Path(project) / name
    if run_dir.exists():
        raise FileExistsError(f"이미 있는 실행이다 — 덮어쓰지 않는다: {run_dir}")
    data = {"train": str((Path(train_dir) / "images").resolve()),
            "val": str((Path(val_dir) / "images").resolve()),
            "names": {str(i): c for i, c in enumerate(train_classes)}}
    data_yaml = run_dir / "data.yaml"
    if write:
        run_dir.mkdir(parents=True)
        data_yaml.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"run_dir": run_dir, "data_yaml": data_yaml, "classes": train_classes,
            "counts": {"train_images": train_images, "val_images": val_images},
            "listing_sha256": {"train": _listing_sha256(train_dir), "val": _listing_sha256(val_dir)}}


def train(plan: dict, epochs: int | None = None) -> Path:
    from ultralytics import YOLO   # 무거운 의존성은 학습할 때만

    import config
    model = YOLO("yolov8n.pt")
    model.train(data=str(plan["data_yaml"]), epochs=epochs or config.EPOCHS,
                batch=config.BATCH_SIZE, workers=config.WORKERS, imgsz=config.IMG_SIZE,
                device=config.resolve_device(), seed=config.TRAIN_SEED,
                project=str(plan["run_dir"].parent), name=plan["run_dir"].name,
                exist_ok=True, verbose=False)
    manifest = {
        "classes": plan["classes"], "counts": plan["counts"], "listing_sha256": plan["listing_sha256"],
        "epochs": epochs or config.EPOCHS, "batch": config.BATCH_SIZE, "imgsz": config.IMG_SIZE,
        "seed": config.TRAIN_SEED, "base_weights": "yolov8n.pt",
        "license_note": "AGPL-3.0(Ultralytics, 학습된 모델 포함) + 학습 자료 조건 — 가중치를 공개하지 않는다",
    }
    (plan["run_dir"] / "ruler_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan["run_dir"] / "weights" / "best.pt"


def main() -> int:
    parser = argparse.ArgumentParser(description="외부 데이터 YOLO 폴더로 자 학습 (yolov8n 미세조정)")
    parser.add_argument("--train", required=True)
    parser.add_argument("--val", required=True, help="학습 검증용 — 적합도 확인용을 쓰지 않는다")
    parser.add_argument("--name", required=True)
    parser.add_argument("--project", default=str(DEFAULT_PROJECT))
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--dry-run", action="store_true", help="준비만 하고 학습하지 않는다")
    args = parser.parse_args()
    plan = prepare(Path(args.train), Path(args.val), Path(args.project), args.name,
                   write=not args.dry_run)
    print(json.dumps({"run_dir": str(plan["run_dir"]), **plan["counts"], "classes": plan["classes"]},
                     ensure_ascii=False))
    if not args.dry_run:
        print("학습 완료 →", train(plan, args.epochs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
