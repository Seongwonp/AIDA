import type { ReviewQueueItem } from "../types";

/**
 * 재검수 목록의 순수 로직.
 *
 * 화면에서 떼어낸 이유는 검사할 수 있게 하려는 것이다. 여기 있는 것들은
 * 눈으로 봐서는 틀린 줄 모르는 종류다 — 이전 저장 형식을 살려 오는 자리,
 * CSV 따옴표 처리, 판정한 뒤 커서를 어디로 옮기는가.
 */
export type Verdict = "hit" | "miss";           // 오류 맞음 | 오류 아님
export type Verdicts = Record<string, Verdict>;

export const STORE = (datasetId: string) => `aida-verdicts-${datasetId}`;
const LEGACY = (datasetId: string) => `aida-reviewed-${datasetId}`;

export function loadVerdicts(datasetId: string): Verdicts {
  try {
    const raw = localStorage.getItem(STORE(datasetId));
    if (raw) return JSON.parse(raw) as Verdicts;
    // 이전 버전은 "봤다"만 배열로 저장했다. 그걸 버리지 않고 "판정 안 함"
    // 상태로 살려 온다 — 검수하던 사람의 진행이 업데이트로 날아가면 안 된다.
    const old = localStorage.getItem(LEGACY(datasetId));
    if (old) {
      const seen = JSON.parse(old) as string[];
      return Object.fromEntries(seen.map((k) => [k, "hit" as Verdict]));
    }
  } catch {
    /* 사생활 보호 모드 등에서 막힐 수 있다 */
  }
  return {};
}

export function keyOf(item: ReviewQueueItem): string {
  return `${item.image}#${item.label_index ?? "none"}#${item.suspicion}`;
}

const VERDICT_TEXT: Record<Verdict, string> = { hit: "오류 맞음", miss: "오류 아님" };

export function toCsv(items: ReviewQueueItem[], verdicts: Verdicts): string {
  // 좌표를 넣는 이유: 받는 쪽이 라벨링 도구다. 이미지 이름만으로는 어느
  // 박스인지 못 찾는다 — 한 장에 스무 개가 들어 있는 게 보통이다.
  const head = ["순위", "이미지", "라벨 인덱스", "의심 유형", "심각도",
                "x1", "y1", "x2", "y2", "근거", "판정"];
  const esc = (v: string | number) => {
    const s = String(v);
    // 쉼표·따옴표·줄바꿈이 들어 있으면 감싸야 한 칸으로 읽힌다
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rows = items.map((i) => {
    const v = verdicts[keyOf(i)];
    // 누락 의심은 가리킬 라벨이 없어 좌표도 없다. 예전 진단 결과에도 없다.
    const box = i.box ?? [];
    const coord = [0, 1, 2, 3].map((k) =>
      box[k] === undefined ? "" : box[k].toFixed(1));
    return [
      i.rank, i.image, i.label_index ?? "", i.label,
      i.severity.toFixed(3), ...coord, i.detail, v ? VERDICT_TEXT[v] : "",
    ].map(esc).join(",");
  });
  // 엑셀이 UTF-8 CSV를 한글로 열려면 BOM이 필요하다
  return "﻿" + [head.join(","), ...rows].join("\n");
}


/**
 * 한 건을 판정한 뒤 커서가 갈 자리.
 *
 * "안 본 것만"이 켜져 있으면 방금 판정한 줄이 목록에서 사라지고 그 자리에
 * 다음 항목이 올라온다. 그래서 인덱스를 **그대로 둬야** 한다 — 평소처럼
 * +1 하면 한 건씩 건너뛴다.
 *
 * @param at 판정한 줄의 인덱스
 * @param shownLength 판정하기 **전**의 목록 길이
 * @param onlyOpen "안 본 것만"이 켜져 있는가
 */
export function nextCursor(at: number, shownLength: number, onlyOpen: boolean): number {
  const next = onlyOpen ? Math.min(at, shownLength - 2) : at + 1;
  return Math.min(Math.max(next, 0), shownLength - 1);
}
