"""KITTI Object Detection (2D) 데이터 다운로드.

라벨 zip(5.6MB)은 전체를 내려받고, 이미지 zip(12.5GB)은 서버가 지원하는
HTTP Range 요청을 이용해 실제로 필요한 이미지(Car 클래스가 포함된 프레임 중
`config.N_TRAIN + config.N_VAL`장)만 부분적으로 내려받는다. 전체 zip을 받지
않아도 되므로 대역폭·시간을 크게 절약한다.

출처: cvlibs.net/datasets/kitti (docs/03-experiment-design.md 2절 참고)
"""
import argparse
import io
import random
import zipfile
from pathlib import Path

import requests
from tqdm import tqdm

import config

LABEL_ZIP_URL = config.KITTI_LABEL_URL
IMAGE_ZIP_URL = config.KITTI_IMAGE_URL

LABEL_ZIP_MEMBER_PREFIX = "training/label_2/"
IMAGE_ZIP_MEMBER_PREFIX = "training/image_2/"


class HTTPRangeFile:
    """zipfile.ZipFile이 요구하는 seek/tell/read를 HTTP Range 요청으로 구현.

    zipfile은 중앙 디렉토리(파일 끝부분)만 먼저 읽고, 이후 실제로 읽으려는
    멤버의 바이트 구간만 요청하기 때문에 전체 파일을 내려받지 않아도 된다.
    """

    def __init__(self, url: str, session: requests.Session | None = None):
        self.url = url
        self.session = session or requests.Session()
        head = self.session.head(url, timeout=30, allow_redirects=True)
        head.raise_for_status()
        if head.headers.get("Accept-Ranges") != "bytes":
            raise RuntimeError(f"{url} 서버가 Range 요청을 지원하지 않습니다")
        self.length = int(head.headers["Content-Length"])
        self.pos = 0

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        elif whence == 2:
            self.pos = self.length + offset
        else:
            raise ValueError(f"invalid whence: {whence}")
        return self.pos

    def tell(self) -> int:
        return self.pos

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            end = self.length - 1
        else:
            end = min(self.pos + size, self.length) - 1
        if end < self.pos:
            return b""
        headers = {"Range": f"bytes={self.pos}-{end}"}
        resp = self.session.get(self.url, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.content
        self.pos += len(data)
        return data


def download_labels(dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    label_dir = dest_dir / "training" / "label_2"
    if label_dir.exists() and any(label_dir.iterdir()):
        print(f"라벨 이미 존재: {label_dir} (스킵)")
        return label_dir

    print("라벨 zip 다운로드 중 (5.6MB)...")
    resp = requests.get(LABEL_ZIP_URL, timeout=120)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        members = [m for m in zf.namelist() if m.startswith(LABEL_ZIP_MEMBER_PREFIX) and m.endswith(".txt")]
        zf.extractall(dest_dir, members=members)
    print(f"라벨 {len(members)}개 추출 완료 → {label_dir}")
    return label_dir


def frames_with_car(label_dir: Path) -> list[str]:
    """Car 클래스를 최소 1개 이상 포함한 프레임 인덱스(예: '000012') 목록."""
    frames = []
    for label_file in sorted(label_dir.glob("*.txt")):
        text = label_file.read_text()
        if any(line.split(" ")[0] == config.TARGET_CLASS for line in text.splitlines() if line.strip()):
            frames.append(label_file.stem)
    return frames


def download_images(frame_ids: list[str], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    missing = [fid for fid in frame_ids if not (dest_dir / f"{fid}.png").exists()]
    if not missing:
        print(f"이미지 이미 전부 존재: {dest_dir} (스킵)")
        return

    print(f"이미지 zip에 Range 요청으로 접속 중 (필요한 {len(missing)}장만 부분 다운로드)...")
    remote = HTTPRangeFile(IMAGE_ZIP_URL)
    with zipfile.ZipFile(remote) as zf:
        for fid in tqdm(missing, desc="이미지 다운로드"):
            member = f"{IMAGE_ZIP_MEMBER_PREFIX}{fid}.png"
            data = zf.read(member)
            (dest_dir / f"{fid}.png").write_bytes(data)
    print(f"이미지 {len(missing)}장 다운로드 완료 → {dest_dir}")


def select_cyclist_rich(label_dir, car_frames: list[str], n_total: int) -> list[str]:
    """Cyclist 인스턴스가 많은 프레임부터 고른다.

    클래스 취약도가 **희소성 때문인지 클래스 자체의 난이도 때문인지** 가르는
    실험용이다. 기존 400장에서 Cyclist는 72개뿐인데 Car는 1851개라, 이 상태로는
    "Cyclist가 취약한 건 드물어서"와 "원래 어려워서"를 구분할 수 없다.

    이미지 장수는 그대로 두고 Cyclist 인스턴스만 늘리므로, 클래스 정체성과
    데이터셋 크기를 고정한 채 개수만 바뀐다. Car 프레임으로 한정하는 건 기존
    선택과 조건을 맞추기 위해서다 — 모든 프레임에 Car가 있어야 Car를 변하지
    않는 기준선으로 쓸 수 있다.
    """
    counted = []
    for stem in car_frames:
        n = sum(1 for line in (label_dir / f"{stem}.txt").read_text().splitlines()
                if line.startswith("Cyclist "))
        counted.append((n, stem))
    # Cyclist 많은 순, 같으면 이름 순 — 시드 없이도 재현되게
    counted.sort(key=lambda x: (-x[0], x[1]))
    chosen = counted[:n_total]
    picked = sum(n for n, _ in chosen)
    expected = sum(n for n, _ in counted) * n_total // len(counted)
    print(f"Cyclist 우선 선택: {n_total}장에 Cyclist {picked}개 "
          f"(무작위였다면 약 {expected}개)")
    return sorted(stem for _n, stem in chosen)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="KITTI 데이터 다운로드 (라벨 전체 + 이미지 부분)")
    parser.add_argument("--n-total", type=int, default=config.N_TRAIN + config.N_VAL,
                         help="다운로드할 총 이미지 수 (기본: config.N_TRAIN + config.N_VAL)")
    parser.add_argument("--seed", type=int, default=config.SEED)
    parser.add_argument("--select", choices=["random", "cyclist_rich"], default=None,
                        help="프레임 선택 전략 (기본: AIDA_FRAME_SELECT, 없으면 random). "
                             "cyclist_rich는 Cyclist가 많은 프레임을 골라 그 클래스의 "
                             "인스턴스 수만 늘린다 — 취약도가 희소성 때문인지 보는 실험용. "
                             "broad(docs/21 AA)는 평가셋 제외 조건이 붙어 별도 스크립트가 "
                             "selected_frames_broad.txt를 만든다")
    args = parser.parse_args(argv)
    strategy = args.select or config.FRAME_SELECT

    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    label_dir = download_labels(config.RAW_DIR)

    car_frames = frames_with_car(label_dir)
    print(f"Car 클래스를 포함한 프레임: {len(car_frames)} / 전체 {len(list(label_dir.glob('*.txt')))}")
    if len(car_frames) < args.n_total:
        raise RuntimeError(f"Car 프레임이 {len(car_frames)}개뿐, 요청한 {args.n_total}개보다 적습니다")

    if strategy == "cyclist_rich":
        selected = select_cyclist_rich(label_dir, car_frames, args.n_total)
    else:
        rng = random.Random(args.seed)
        selected = sorted(rng.sample(car_frames, args.n_total))

    selection_file = (config.RAW_DIR / ("selected_frames.txt" if strategy == "random"
                                        else f"selected_frames_{strategy}.txt"))
    selection_file.write_text("\n".join(selected) + "\n")
    print(f"{len(selected)}개 프레임 선택 (전략={strategy}) → {selection_file}")

    image_dir = config.RAW_DIR / "training" / "image_2"
    download_images(selected, image_dir)
    print("다운로드 완료.")


if __name__ == "__main__":
    main()
