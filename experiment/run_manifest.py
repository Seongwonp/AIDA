"""실행 명세 — 이 결과를 무엇으로 만들었는지 (docs/25 2단계).

**시드만으로 분할 보존을 대신하지 않는다.** 분할은 시드로 결정되지만 그것은
**같은 프레임 풀**을 전제로 한다. 풀 파일(`selected_frames*.txt`)은 저장소에
없고, 원본 데이터가 달라지면 같은 시드로도 다른 분할이 나온다.

그래서 실제 목록과 해시를 남긴다.

  분할      학습·평가 프레임 id 전부 + 그 목록의 해시
  이미지    분할에 든 이미지 파일의 내용 해시 (원본이 바뀌면 달라진다)
  가중치    best.pt의 해시와 학습 설정
  코드      git 커밋과 작업 트리가 깨끗한지
  의존성    python·torch·ultralytics 판
  설정      클래스 구성·데이터셋·프레임 선택·규모·에폭·시드

사용법:
  python run_manifest.py --out manifests/기본.json
  python run_manifest.py --runs runs_mc_cyclist_rich/clean --out ...
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config  # noqa: E402


def sha256_of(path: Path, chunk: int = 1 << 20) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            while block := f.read(chunk):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def digest_of_list(items: list[str]) -> str:
    """목록 자체의 해시. 순서를 정렬해 담아 재현 가능하게 한다."""
    return hashlib.sha256("\n".join(sorted(items)).encode("utf-8")).hexdigest()


def git_state() -> dict:
    def run(*args: str) -> str | None:
        try:
            out = subprocess.run(["git", *args], capture_output=True, text=True,
                                 cwd=str(config.EXPERIMENT_ROOT), timeout=20)
            return out.stdout.strip() if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    status = run("status", "--porcelain")
    return {
        "commit": run("rev-parse", "HEAD"),
        # **깨끗하지 않으면 그 사실을 남긴다.** 커밋만 적어두면 재현할 때
        # 없는 상태를 재현하려 하게 된다.
        "clean": status == "" if status is not None else None,
    }


def dependency_versions() -> dict:
    out: dict[str, str | None] = {"python": sys.version.split()[0]}
    for name in ("torch", "ultralytics", "PIL", "numpy"):
        try:
            mod = __import__(name)
            out[name] = getattr(mod, "__version__", None)
        except Exception:
            out[name] = None            # 이 환경에 없다 — 없다고 적는다
    return out


def split_record(hash_images: bool) -> dict:
    """지금 설정이 만드는 학습·평가 분할."""
    from data_loader import split_frames

    pool_file = config.SELECTED_FRAMES_FILE
    if not pool_file.exists():
        return {"error": f"{pool_file.name} 없음 — 분할을 되살릴 수 없다"}
    pool = [ln.strip() for ln in pool_file.read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    train, val = split_frames(pool)

    record: dict = {
        "pool_file": pool_file.name,
        "pool_size": len(pool),
        "pool_digest": digest_of_list(pool),
        "train": train,
        "val": val,
        "train_digest": digest_of_list(train),
        "val_digest": digest_of_list(val),
    }
    if hash_images:
        # **원본이 바뀌었는지**는 목록만으로는 모른다. 같은 이름의 다른 그림일
        # 수 있다. 분할에 든 것만 내용 해시를 뜬다.
        images: dict[str, str | None] = {}
        for stem in train + val:
            for suffix in (".png", ".jpg", ".jpeg"):
                p = config.IMAGES_TRAIN_DIR / f"{stem}{suffix}"
                if p.exists():
                    images[p.name] = sha256_of(p)
                    break
        record["image_hashes"] = images
        record["image_digest"] = digest_of_list(
            [f"{k}:{v}" for k, v in images.items() if v])
    return record


def weights_record(run_dirs: list[str]) -> list[dict]:
    out = []
    for rel in run_dirs:
        d = config.EXPERIMENT_ROOT / rel
        best = d / "weights" / "best.pt"
        entry: dict = {"run": rel, "exists": best.exists()}
        if best.exists():
            entry["sha256"] = sha256_of(best)
            entry["bytes"] = best.stat().st_size
            args = d / "args.yaml"
            if args.exists():
                import yaml
                try:
                    a = yaml.safe_load(args.read_text(encoding="utf-8")) or {}
                    entry["train_args"] = {k: a.get(k) for k in
                                           ("epochs", "batch", "imgsz", "seed",
                                            "model", "optimizer")}
                except Exception:
                    entry["train_args"] = None
        out.append(entry)
    return out


def build(run_dirs: list[str], hash_images: bool) -> dict:
    return {
        "settings": {
            "classes": config.CLASS_NAMES,
            "dataset": config.DATASET,
            "frame_select": config.FRAME_SELECT,
            "n_train": config.N_TRAIN,
            "n_val": config.N_VAL,
            "epochs": config.EPOCHS,
            "batch_size": config.BATCH_SIZE,
            "img_size": config.IMG_SIZE,
            "error_ratio": config.ERROR_RATIO,
            "val_holdout": config.VAL_HOLDOUT,
        },
        "seeds": {
            "split": config.SEED,
            "error": config.ERROR_SEED,
        },
        "code": git_state(),
        "dependencies": dependency_versions(),
        "split": split_record(hash_images),
        "weights": weights_record(run_dirs),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="실행 명세를 남긴다")
    ap.add_argument("--runs", nargs="*", default=[],
                    help="가중치를 남길 실행 폴더 (예: runs_coco/clean)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--no-image-hashes", action="store_true",
                    help="이미지 내용 해시를 건너뛴다 (빠르지만 원본 변경을 못 잡는다)")
    args = ap.parse_args()

    manifest = build(args.runs, not args.no_image_hashes)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    split = manifest["split"]
    print(f"→ {args.out}")
    if "error" in split:
        print(f"  분할: {split['error']}")
    else:
        print(f"  분할: 학습 {len(split['train'])} · 평가 {len(split['val'])} "
              f"(풀 {split['pool_size']})")
        print(f"  분할 해시: {split['train_digest'][:16]} / {split['val_digest'][:16]}")
    print(f"  코드: {manifest['code']['commit']} "
          f"({'깨끗' if manifest['code']['clean'] else '변경 있음'})")
    for w in manifest["weights"]:
        mark = w.get("sha256", "없음")
        print(f"  가중치 {w['run']}: {mark[:16] if w.get('sha256') else mark}")


if __name__ == "__main__":
    main()
