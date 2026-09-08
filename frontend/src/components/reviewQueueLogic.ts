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
  } catch {
    /* 사생활 보호 모드 등에서 막힐 수 있다 */
  }
  return {};
}

/**
 * 이전 형식이 남긴 "봤다" 목록 (docs/24 B1).
 *
 * **판정이 아니다.** 예전 버전은 본 것만 배열로 저장했는데, 그것을 예전 코드는
 * `hit`("오류 맞음")으로 읽어 들였다. 주석에는 "판정 안 함 상태로 살려 온다"고
 * 적혀 있었지만 코드는 그렇지 않았고, 그러면 **이 데이터셋의 정밀도가
 * 100%로 보고된다** — 화면의 정밀도는 `오류 맞음 ÷ 판정한 것`이라 보기만 한
 * 것이 전부 맞은 것으로 세어진다.
 *
 * 진행은 살리되 판정으로는 세지 않는다. 화면은 "안 본 것만" 필터에서만 쓴다.
 */
export function loadSeen(datasetId: string): Set<string> {
  try {
    const old = localStorage.getItem(LEGACY(datasetId));
    if (old) return new Set(JSON.parse(old) as string[]);
  } catch {
    /* 위와 같다 */
  }
  return new Set();
}

/**
 * 판정을 매다는 키 (docs/24 B1).
 *
 * **순서가 바뀌어도 같아야 하고, 후보가 다르면 달라야 한다.** 순위(rank)를 쓰면
 * 안 되는 이유가 그것이다 — 순서 규칙을 이미 두 번 바꿨다(docs/21 AN·AO).
 *
 * `label_index`는 라벨을 가리키므로 그 자체로 후보를 구분한다. 그런데 **누락
 * 의심은 대응하는 라벨이 없어 null**이다(`label_diagnosis.BoxFinding` 주석).
 * 그래서 이미지 한 장에 누락 후보가 여럿이면 키가 전부 같아졌고, 하나를
 * 판정하면 나머지도 판정된 것으로 보였다.
 *
 * 그때만 좌표를 덧붙인다. 라벨 인덱스가 있는 후보의 키는 **예전 그대로**라
 * 이미 저장된 판정이 살아난다.
 */
export function keyOf(item: ReviewQueueItem): string {
  const base = `${item.image}#${item.label_index ?? "none"}#${item.suspicion}`;
  if (item.label_index !== null && item.label_index !== undefined) return base;
  // box는 나중에 추가된 필드라 예전 진단 결과에는 없다(types.ts).
  return `${base}#${item.box ? item.box.join(",") : "nobox"}`;
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

/**
 * 이 데이터셋의 판정을 브라우저에서 지운다.
 *
 * 데이터셋을 지우면 서버에서는 폴더째 사라지는데 판정은 남는다. 사용자가
 * "지우기"를 누른 이유는 대개 고객 데이터를 치우려는 것이라, 어느 이미지의
 * 몇 번 박스가 오류였는지가 남아 있으면 기대와 다르다.
 *
 * 옛 형식 키도 같이 지운다 — 하나만 지우면 다음에 열 때 되살아난다.
 */
export function clearVerdicts(datasetId: string): void {
  try {
    localStorage.removeItem(STORE(datasetId));
    localStorage.removeItem(LEGACY(datasetId));
  } catch {
    /* 막혀 있으면 애초에 저장된 것도 없다 */
  }
}

/**
 * 판정이 어디에 남았고 어디에 못 남았는지 (docs/24 B1).
 *
 * 예전에는 서버 저장 실패를 조용히 삼켰다(`.catch(() => {})`). 브라우저에는
 * 남으므로 검수는 이어지지만, **다른 기계에서 이어받을 수 없게 된 것을 아무도
 * 모른다.** 검수는 막지 않되 사실은 말한다.
 *
 * 빈 문자열이면 둘 다 성공한 것이고 화면에 아무것도 띄우지 않는다.
 */
export function saveStatusMessage(serverFailed: boolean, localFailed: boolean): string {
  if (serverFailed && localFailed)
    return "판정을 서버에도 이 브라우저에도 저장하지 못했습니다. 지금 창을 닫으면 사라집니다.";
  if (serverFailed)
    return "판정을 서버에 저장하지 못했습니다. 이 브라우저에는 남아 있지만 다른 기계에서는 이어받을 수 없습니다.";
  if (localFailed)
    return "판정을 이 브라우저에 저장하지 못했습니다. 서버에는 남았습니다.";
  return "";
}
