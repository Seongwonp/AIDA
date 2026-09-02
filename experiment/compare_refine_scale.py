"""자기 정제의 손익을 데이터 규모별로 분해한다 (docs/21 W·X).

W는 400장에서 정제가 진다고 결론냈다. 이유는 "이미지를 반 버리는 손해(-0.181)가
오류가 주던 손해(-0.103)보다 크다"였다. 그런데 400장은 YOLOv8n에게 너무 적어서,
그 손해가 규모 탓일 수 있었다.

같은 분해를 800장에서 반복해 교환 비율이 뒤집히는지 본다.

  전체N장 · 오류 0%   (clean)          상한
  전체N장 · 오류 30%  (scale_m30)      정제 안 함
  절반   · 오류 0%    (clean_sub)      데이터 손해만 분리한 대조군
  절반   · 오류 ~12%  (refined50)      정제한 것

사용법:
  python compare_refine_scale.py
"""
import sys

import pandas as pd

import config

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA = config.EXPERIMENT_ROOT.parent / "backend" / "app" / "data"
SETUPS = [
    ("400장", "metrics_mc.csv", "clean_sub200", 400, 200),
    ("800장", "metrics_mc_all_local_n800.csv", "clean_sub400", 800, 400),
]


def main() -> None:
    rows = []
    for label, csv, ctrl, full, half in SETUPS:
        path = DATA / csv
        if not path.exists():
            print(f"[{label}] {csv} 없음 — 건너뜀")
            continue
        df = pd.read_csv(path).set_index("condition")
        need = ["clean", "scale_m30", ctrl, "scale_m30_refined50"]
        missing = [c for c in need if c not in df.index]
        if missing:
            print(f"[{label}] 아직 없는 조건: {missing}")
            continue
        g = lambda c: float(df.loc[c, "map50"])
        rows.append((label, full, half, g("clean"), g("scale_m30"),
                     g(ctrl), g("scale_m30_refined50")))

    if not rows:
        raise SystemExit("비교할 데이터가 없습니다")

    print(f"{'규모':<8}{'전체·오류0%':>12}{'전체·오류30%':>13}"
          f"{'절반·오류0%':>13}{'절반·오류12%':>13}")
    print("-" * 60)
    for label, full, half, c, s, ctrl, ref in rows:
        print(f"{label:<8}{c:>12.3f}{s:>13.3f}{ctrl:>13.3f}{ref:>13.3f}")

    print(f"\n{'규모':<8}{'절반 버리는 손해':>18}{'오류 30%의 손해':>17}"
          f"{'정제로 얻을 천장':>18}")
    print("-" * 62)
    for label, full, half, c, s, ctrl, ref in rows:
        data_loss = c - ctrl          # 라벨은 깨끗한 채 이미지만 반으로
        error_loss = c - s            # 이미지는 그대로 두고 오류만
        ceiling = ctrl - ref          # 남은 오류를 완벽히 지웠을 때의 이득
        print(f"{label:<8}{data_loss:>17.3f}{error_loss:>17.3f}{ceiling:>18.3f}")

    print("\n정제가 이기려면 '정제로 얻을 천장'이 '절반 버리는 손해'보다 커야 한다.")
    for label, full, half, c, s, ctrl, ref in rows:
        data_loss, ceiling = c - ctrl, ctrl - ref
        verdict = "정제가 이긴다" if ceiling > data_loss else "정제가 진다"
        ratio = ceiling / data_loss if data_loss else float("inf")
        print(f"  {label}: 천장 {ceiling:.3f} vs 손해 {data_loss:.3f} "
              f"= {ratio:.2f}배 → {verdict}")


if __name__ == "__main__":
    main()
