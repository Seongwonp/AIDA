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
            # **인코딩을 못 박는다.** 한글 파일 이름이 섞이면 기본 코드페이지
            # (cp949)로는 디코드가 깨지고, 그러면 git 상태를 못 읽은 것과
            # 구분이 안 된다 — 더러운 트리를 깨끗하다고 적을 뻔했다.
            out = subprocess.run(["git", *args], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace",
                                 cwd=str(config.EXPERIMENT_ROOT), timeout=20)
            return out.stdout.strip() if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    status = run("status", "--porcelain")
    # 상태를 못 읽으면 **깨끗하다고 하지 않는다.** None은 "모른다"다.
    clean = (status == "") if status is not None else None
    state: dict = {
        "commit": run("rev-parse", "HEAD"),
        # **깨끗하지 않으면 그 사실을 남긴다.** 커밋만 적어두면 재현할 때
        # 없는 상태를 재현하려 하게 된다.
        "clean": clean,
    }
    if clean is False:
        diff = run("diff", "HEAD")
        # 커밋되지 않은 변경의 해시. **이것으로 재현할 수 있다는 뜻이 아니다** —
        # diff 내용 자체는 어디에도 안 남으므로, 나중에 같은 상태인지 대조만
        # 할 수 있다. 추적 안 되는 새 파일은 diff에도 안 잡힌다.
        state["uncommitted_diff_sha256"] = (
            hashlib.sha256(diff.encode("utf-8")).hexdigest() if diff is not None else None)
        state["reproducible"] = False
        state["reproducible_reason"] = (
            "작업 트리에 커밋되지 않은 변경이 있다 — 이 실행은 정확 재현이 안 된다")
    else:
        state["reproducible"] = clean
    return state


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
        #
        # **학습과 평가는 다른 폴더에 있다.** 둘 다 학습 폴더에서 찾으면 평가
        # 이미지의 해시가 조용히 빠지고, 그 명세는 완전해 보인다.
        images: dict[str, str | None] = {}
        missing: list[str] = []
        # **논리적 분할과 파일이 놓인 자리는 다르다.** 학습 목록의 프레임이
        # images/val에 있기도 하다 — 물리적 배치는 내려받기 단계가 정하고
        # 분할은 시드가 정하기 때문이다. 그래서 **양쪽을 다 찾되 어디서
        # 찾았는지 적는다.**
        located: dict[str, str] = {}
        for split, stems in (("train", train), ("val", val)):
            for stem in stems:
                found = None
                for directory, where in ((config.IMAGES_TRAIN_DIR, "images/train"),
                                         (config.IMAGES_VAL_DIR, "images/val")):
                    for suffix in (".png", ".jpg", ".jpeg"):
                        candidate = directory / f"{stem}{suffix}"
                        if candidate.exists():
                            found, found_in = candidate, where
                            break
                    if found is not None:
                        break
                # 같은 이름이 양쪽에 있어도 안 섞이게 split을 키에 넣는다.
                key = f"{split}/{stem}"
                if found is None:
                    missing.append(key)
                    continue
                images[key] = sha256_of(found)
                located[key] = found_in
        record["image_locations"] = located

        record["image_hashes"] = images
        record["image_digest"] = digest_of_list(
            [f"{k}:{v}" for k, v in images.items() if v])
        # **불완전한 명세가 완전한 명세처럼 보이면 안 된다.**
        record["missing_images"] = missing
        record["complete"] = not missing and all(images.values())
    else:
        # 해시를 안 떴으면 완전하다고 말할 수 없다.
        record["complete"] = False
        record["complete_reason"] = "이미지 해시를 건너뜀(--no-image-hashes)"
    return record


def weights_record(run_dirs: list[str], sources: dict[str, str] | None = None) -> list[dict]:
    """가중치의 해시와 **출처**.

    해시는 "이 파일이 그 파일인가"만 말한다. 로드맵이 요구한 것은 출처다 —
    어떤 실행이 이 가중치를 만들었는가. 우리는 그것을 자동으로 알 방법이 없어
    (실행 폴더 이름은 조건 이름이지 출처가 아니다) **모르면 unknown으로 적는다.**
    추측해 채우지 않는다.
    """
    sources = sources or {}
    out = []
    for rel in run_dirs:
        d = config.EXPERIMENT_ROOT / rel
        best = d / "weights" / "best.pt"
        entry: dict = {"run": rel, "exists": best.exists(),
                       "source": sources.get(rel, "unknown")}
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


# 명세의 모양이 바뀌면 올린다. 옛 명세를 새 코드로 읽을 때 필요하다.
MANIFEST_SCHEMA_VERSION = 1


def build(run_dirs: list[str], hash_images: bool,
          sources: dict[str, str] | None = None) -> dict:
    code = git_state()
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
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
        "code": code,
        "dependencies": dependency_versions(),
        "split": split_record(hash_images),
        "weights": weights_record(run_dirs, sources),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="실행 명세를 남긴다")
    ap.add_argument("--runs", nargs="*", default=[],
                    help="가중치를 남길 실행 폴더 (예: runs_coco/clean)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--no-image-hashes", action="store_true",
                    help="이미지 내용 해시를 건너뛴다 (빠르지만 원본 변경을 못 잡는다)")
    ap.add_argument("--source", action="append", default=[], metavar="실행=출처",
                    help="가중치 출처. 예: --source runs_coco/clean=train_coco_rulers.sh")
    args = ap.parse_args()

    sources = {}
    for item in args.source:
        run_name, _, origin = item.partition("=")
        if not origin:
            raise SystemExit(f"--source는 실행=출처 꼴이어야 합니다: {item!r}")
        sources[run_name] = origin

    manifest = build(args.runs, not args.no_image_hashes, sources)
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
        print(f"  완전한가: {'예' if split.get('complete') else '아니오'}"
              + (f" (빠진 이미지 {len(split['missing_images'])}장)"
                 if split.get("missing_images") else ""))
    code = manifest["code"]
    print(f"  코드: {code['commit']} "
          f"({'깨끗' if code['clean'] else '변경 있음 — 정확 재현 불가'})")
    for w in manifest["weights"]:
        mark = w.get("sha256", "없음")
        print(f"  가중치 {w['run']}: {mark[:16] if w.get('sha256') else mark}")


if __name__ == "__main__":
    main()
