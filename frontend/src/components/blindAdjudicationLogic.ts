/**
 * 가림 판정의 순수 로직 (docs/evaluation-adjudication-design.md).
 *
 * **제품의 재검수 판정과 다른 것이 셋이다.**
 *
 *   1. 순위·점수·의심 유형을 **안 보여준다.** 보고 판단하면 그 순위를 평가할 수
 *      없다 — 자기가 만든 순서를 자기가 확인해 주는 셈이 된다.
 *   2. `hold`가 있다. "모르겠다"를 `miss`로 밀어 넣으면 정밀도가 낮게 나오고,
 *      `hit`으로 밀면 높게 나온다. 어느 쪽도 사실이 아니다.
 *   3. **누락 객체는 어느 객체인지까지 정해야 한다.** 겹쳐 잡은 후보 둘을 서로
 *      다른 오류로 세면 고유 오류 수가 부풀려진다.
 *
 * 화면 상태를 여기서 다루고 React는 그리기만 한다 — 순수 함수라 검사에서
 * 브라우저 없이 규칙을 고정할 수 있다.
 */

export type EvalVerdict = "hit" | "miss" | "hold";

export type BlindCandidate = {
  canonical_candidate_id: string;
  image: string;
  label_index: number | null;
  box: number[] | null;
  verdict: EvalVerdict | null;
  unique_error_id: string | null;
};

/** 후보 하나에 대해 화면이 들고 있는 것. */
export type Judgement = {
  verdict: EvalVerdict | null;
  /** 누락 객체 이름(`M1`). 기존 라벨은 서버가 정하므로 비어 있다. */
  missingObject?: string | null;
};

export type Judgements = Record<string, Judgement>;

export const MISSING_NEEDS_OBJECT =
  "누락을 오류로 판정하려면 어느 객체인지 골라야 합니다. 겹쳐 잡은 후보 둘을 " +
  "서로 다른 오류로 세면 고유 오류 수가 부풀려집니다.";

export const HASH_CONFLICT_MESSAGE =
  "후보 목록이 그 사이에 바뀌었습니다. 이 판정이 무엇을 가리키는지 알 수 없어 " +
  "저장하지 않았습니다. 화면을 새로 여세요.";

export const DAMAGED_MESSAGE =
  "저장된 판정 파일을 읽지 못했습니다. 빈 판정으로 시작하지 않으니, 덮어쓰기 " +
  "전에 파일을 확인하세요.";

/** 서버가 준 목록을 화면 상태로. **없는 판정은 `null`이고 `hold`가 아니다.** */
export function toJudgements(candidates: BlindCandidate[]): Judgements {
  const out: Judgements = {};
  for (const c of candidates) {
    out[c.canonical_candidate_id] = {
      verdict: c.verdict,
      missingObject: missingName(c.image, c.unique_error_id),
    };
  }
  return out;
}

/**
 * `a.jpg/M1` → `M1`. 그 이미지의 것이 아니면 `null`.
 *
 * 이미지는 서버가 붙인다. 화면은 이미지 안의 번호만 다룬다.
 */
export function missingName(image: string, uniqueErrorId: string | null | undefined): string | null {
  if (!uniqueErrorId) return null;
  if (/^M\d+$/.test(uniqueErrorId)) return uniqueErrorId;
  const cut = uniqueErrorId.lastIndexOf("/");
  if (cut < 0) return null;
  if (uniqueErrorId.slice(0, cut) !== image) return null;
  const name = uniqueErrorId.slice(cut + 1);
  return /^M\d+$/.test(name) ? name : null;
}

/**
 * 이 이미지에서 이미 만든 누락 객체들. 번호 순.
 *
 * 판정자는 **새로 만들거나 이미 만든 것에 연결한다.** 목록이 없으면 연결할
 * 방법이 없어 겹친 후보가 서로 다른 오류가 된다.
 */
export function missingObjects(
  candidates: BlindCandidate[],
  judgements: Judgements,
  image: string,
): string[] {
  const names = new Set<string>();
  for (const c of candidates) {
    if (c.image !== image) continue;
    const name = judgements[c.canonical_candidate_id]?.missingObject;
    if (name) names.add(name);
  }
  return [...names].sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)));
}

/** 이 이미지의 다음 누락 객체 이름. 빈 번호를 재사용하지 않는다. */
export function nextMissingObject(
  candidates: BlindCandidate[],
  judgements: Judgements,
  image: string,
): string {
  const used = missingObjects(candidates, judgements, image);
  const max = used.reduce((m, n) => Math.max(m, Number(n.slice(1))), 0);
  return `M${max + 1}`;
}

/** 저장할 수 없는 판정들. **비어 있어야 보낸다.** */
export function blockedIds(candidates: BlindCandidate[], judgements: Judgements): string[] {
  return candidates
    .filter((c) => {
      const j = judgements[c.canonical_candidate_id];
      return c.label_index === null && j?.verdict === "hit" && !j.missingObject;
    })
    .map((c) => c.canonical_candidate_id);
}

/** 서버에 보낼 모양. `blockedIds`가 비어 있을 때만 부른다. */
export function toRequest(candidates: BlindCandidate[], judgements: Judgements) {
  return candidates
    .filter((c) => judgements[c.canonical_candidate_id]?.verdict !== undefined)
    .map((c) => {
      const j = judgements[c.canonical_candidate_id];
      const hit = j?.verdict === "hit";
      return {
        canonical_candidate_id: c.canonical_candidate_id,
        verdict: j?.verdict ?? null,
        // 기존 라벨은 서버가 정한다. 누락만 화면이 정한다.
        unique_error_id: hit && c.label_index === null ? (j?.missingObject ?? null) : null,
      };
    });
}

/**
 * 판정 진행 상황. **보류도 센다** — 사람이 시간을 썼다.
 *
 * `hit` 비율은 여기서 계산하지 않는다. 화면에 정밀도가 뜨면 판정자가 그것을
 * 보고 다음 판정을 조절하게 된다.
 */
export function progress(candidates: BlindCandidate[], judgements: Judgements) {
  const judged = candidates.filter(
    (c) => judgements[c.canonical_candidate_id]?.verdict != null,
  ).length;
  const blocked = blockedIds(candidates, judgements).length;
  return { total: candidates.length, judged, blocked, left: candidates.length - judged };
}

/**
 * 저장 요청을 **한 번에 하나씩** 보낸다 (docs/25 R2와 같은 규칙).
 *
 * 병렬로 보내면 늦게 출발한 요청이 먼저 도착해 옛 판정이 최종본이 된다. 전체
 * 교체 API라 그 한 번으로 이후 판정이 통째로 사라진다.
 */
export function makeAdjudicationSender<T>(
  send: (rows: T) => Promise<unknown>,
): (rows: T) => Promise<boolean> {
  let inFlight = false;
  let queued: { rows: T } | null = null;
  let waiters: Array<(ok: boolean) => void> = [];

  const flush = async (): Promise<void> => {
    while (queued !== null) {
      const next = queued.rows;
      queued = null;
      const settle = waiters;
      waiters = [];
      let ok = true;
      try {
        // 순차 실행이 이 함수의 목적이다. 병렬로 보내면 순서가 뒤집힌다.
        await send(next);
      } catch {
        ok = false;
      }
      settle.forEach((f) => f(ok));
    }
    inFlight = false;
  };

  return (rows: T) => {
    queued = { rows };                       // 중간 상태는 덮어쓴다
    const done = new Promise<boolean>((resolve) => waiters.push(resolve));
    if (!inFlight) {
      inFlight = true;
      void flush();
    }
    return done;
  };
}

/** 저장 상태 문구. 실패를 조용히 넘기지 않는다. */
export function saveMessage(state: "saving" | "saved" | "failed" | "idle"): string {
  if (state === "saving") return "저장 중…";
  if (state === "saved") return "저장됨";
  if (state === "failed") return "저장하지 못했습니다. 다시 시도를 누르세요.";
  return "";
}
