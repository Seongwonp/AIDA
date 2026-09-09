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
    // 누락 의심에도 좌표는 **있다** — "있어야 할 자리"인 예측 박스가 들어간다
  // (diagnose_labels의 review_queue 주석). 라벨이 없을 뿐이다. 좌표가 비는
  // 것은 이 기능 전에 만든 예전 진단 결과뿐이다.
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

/**
 * 판정을 브라우저에 저장한다. 성공하면 true (docs/24 B2).
 *
 * 화면 두 곳에서 같은 try/catch를 쓰고 있었다. 저장 성공 여부가 화면에
 * 드러나야 하므로(B1) 한 군데로 모으고 결과를 돌려준다.
 */
export function saveVerdicts(datasetId: string, verdicts: Verdicts): boolean {
  try {
    localStorage.setItem(STORE(datasetId), JSON.stringify(verdicts));
    return true;
  } catch {
    return false;   // 사생활 보호 모드·용량 초과. 이번 세션에는 반영된다
  }
}

/**
 * 내려받는 CSV가 **전체인지 화면에 보이는 것만인지** (docs/24 B2).
 *
 * 내려받기는 걸러진 목록(`shown`)을 쓴다. 유형으로 좁히거나 "안 본 것만"을
 * 켜 둔 채 내려받으면 일부만 나가는데, 예전에는 그 사실이 화면에 없었다.
 * 받는 쪽은 라벨링 도구라 **빠진 줄을 "오류 아님"으로 오해할 수 있다.**
 */
export function csvScopeNote(shownCount: number, totalCount: number): string {
  if (shownCount >= totalCount) return `전체 ${totalCount}건을 내려받습니다.`;
  return `화면에 보이는 ${shownCount}건만 내려받습니다 (전체 ${totalCount}건).`;
}

/**
 * 서버 저장을 **한 줄로 세운다** (docs/25 R2).
 *
 * 판정은 전체 교체 API로 올라간다. 그래서 두 요청이 순서 바뀌어 도착하면
 * **먼저 보낸 옛 상태가 나중에 도착해 최신을 지운다.** 실제 화면 검사로
 * 재현했다(`ReviewQueue.order.test.tsx`).
 *
 * 고치는 방법이 둘이었다.
 *
 *   1. 서버에 버전을 붙여 오래된 요청을 거절한다.
 *   2. 클라이언트가 앞 요청이 끝난 뒤에 다음을 보낸다.
 *
 * **2를 골랐다.** 지금 동시성의 범위가 "한 사람이 한 자리에서" 이고(사용자
 * 개념도 인증도 없다), 서버 버전 검사는 API와 파일 형식을 함께 바꿔야 한다.
 * 작은 쪽으로 먼저 막는다.
 *
 * **중간 상태는 건너뛴다.** 기다리는 동안 판정이 세 번 더 오면 마지막 것만
 * 보낸다 — 전체 교체 API라 중간 것을 보낼 이유가 없다.
 *
 * **한계.** 이것은 **한 탭 안의 순서**만 지킨다. 탭이 둘이면 서로의 순서를
 * 모른다(docs/25 R2의 남은 항목).
 */
export function makeVerdictSender(
  send: (verdicts: Verdicts) => Promise<unknown>,
): (verdicts: Verdicts) => Promise<boolean> {
  let inFlight = false;
  let queued: Verdicts | null = null;
  let waiters: Array<(ok: boolean) => void> = [];

  const flush = async (): Promise<void> => {
    while (queued !== null) {
      const next = queued;
      queued = null;
      const settle = waiters;
      waiters = [];
      let ok = true;
      try {
        // no-await-in-loop 경고가 뜨지만 순차 실행이 이 함수의 목적이다.
        // 병렬로 보내면 순서가 다시 뒤집힌다(docs/25 R2).
        await send(next);
      } catch {
        ok = false;
      }
      settle.forEach((f) => f(ok));
    }
    inFlight = false;
  };

  return (verdicts: Verdicts) => {
    queued = verdicts;                       // 중간 상태는 덮어쓴다
    const done = new Promise<boolean>((resolve) => waiters.push(resolve));
    if (!inFlight) {
      inFlight = true;
      void flush();
    }
    return done;
  };
}

/**
 * 다른 탭이 같은 데이터셋을 고쳤는가 (docs/25 R2).
 *
 * 저장 직렬화는 **한 탭 안의 순서**만 지킨다. 탭이 둘이면 서로의 요청을 모르고,
 * 전체 교체 API라 나중 탭이 앞 탭의 판정을 통째로 지운다.
 *
 * **막지 않고 알린다.** 지금 동시성의 범위가 "한 사람"이라 잠금을 걸 상대가
 * 없고, 검수를 멈추게 하는 쪽이 이 제품의 방침과 어긋난다(서버가 죽어도 검수는
 * 이어진다). 대신 다른 탭이 고쳤다는 것을 화면에 말한다.
 *
 * `storage` 이벤트는 **다른 탭에서만** 온다 — 자기 탭의 setItem은 안 잡힌다.
 * 그래서 별도 표시 없이 이것만으로 갈린다.
 */
export function otherTabChanged(event: StorageEvent, datasetId: string): boolean {
  return event.key === STORE(datasetId) && event.newValue !== null;
}

export const OTHER_TAB_MESSAGE =
  "다른 탭에서 같은 데이터셋의 판정을 바꿨습니다. 이 탭에서 계속 판정하면 " +
  "그쪽 판정을 덮어쓸 수 있습니다. 새로고침해서 합친 상태를 먼저 확인하세요.";

/**
 * 서버가 빈 판정을 줬을 때 브라우저 사본을 살릴 것인가 (docs/25 R3).
 *
 * **서버가 비는 이유가 셋이고 뜻이 다르다.**
 *
 * | 서버 응답 | 뜻 | 브라우저 사본 |
 * |---|---|---|
 * | 판정 없음 · `updated_at` 없음 | 아직 아무것도 저장 안 됨 | **살린다** — 유일한 원본이다 |
 * | 판정 없음 · `updated_at` 있음 | **전부 지웠다** | **버린다** — 지운 것이 최신이다 |
 * | 응답 자체가 실패 | 판단할 근거가 없다 | 살린다 (이어서 검수) |
 *
 * 가운데가 문제였다. 화면이 "비었으면 브라우저 것을 쓴다"로만 되어 있어
 * **지운 판정이 되살아났다.** `updated_at`은 한 번이라도 저장하면 값이 생기므로
 * 그것으로 갈린다.
 *
 * **기준 원본은 서버다.** 브라우저 사본은 서버가 아무 말도 못 할 때만 원본이 된다.
 */
export function shouldKeepLocalOnEmpty(updatedAt: string | null | undefined): boolean {
  return !updatedAt;
}
