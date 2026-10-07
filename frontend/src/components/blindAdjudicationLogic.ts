/**
 * 가림 판정의 순수 로직 (docs/evaluation-adjudication-design.md).
 *
 * **제품의 재검수 판정과 다른 것이 셋이다.**
 *
 *   1. 순위·점수·의심 유형을 **안 보여준다.** 보고 판단하면 그 순위를 평가할 수
 *      없다 — 자기가 만든 순서를 자기가 확인해 주는 셈이 된다.
 *   2. `hold`("판단 보류")가 있다. 보류를 `miss`로 밀어 넣으면 정밀도가 낮게 나오고,
 *      `hit`으로 밀면 높게 나온다. 어느 쪽도 사실이 아니다.
 *   3. **누락 객체는 어느 객체인지까지 정해야 한다.** 겹쳐 잡은 후보 둘을 서로
 *      다른 오류로 세면 고유 오류 수가 부풀려진다.
 *
 * 화면 상태를 여기서 다루고 React는 그리기만 한다 — 순수 함수라 검사에서
 * 브라우저 없이 규칙을 고정할 수 있다.
 */

export type EvalVerdict = "hit" | "miss" | "hold";

/**
 * 판정 단추 — **단추 글자가 곧 판정 결과다.** 두 질문 모두 "예"가 오류다.
 *
 * | 단추 | 단축키 | 저장값 |
 * |---|---|---|
 * | 오류 있음 | 1 | `hit` |
 * | 오류 없음 | 2 | `miss` |
 * | 판단 보류 | 3 | `hold` |
 *
 * 질문 문구를 바꿀 때 이 대응을 뒤집지 않는다 — 저장값의 뜻은 연습 판정과 본 판정에서 같아야 한다.
 */
export const VERDICT_BUTTONS = [
  { verdict: "hit", label: "오류 있음", key: "1" },
  { verdict: "miss", label: "오류 없음", key: "2" },
  { verdict: "hold", label: "판단 보류", key: "3" },
] as const satisfies ReadonlyArray<{ verdict: EvalVerdict; label: string; key: string }>;

/** 후보 층마다 묻는 질문. 기존 라벨은 "고쳐야 하는가", 누락은 "빠졌는가" — 둘 다 "예"가 오류 있음이다. */
export const QUESTION_EXISTING = "이 라벨은 수정이 필요한가?";
export const QUESTION_MISSING = "이 객체의 라벨이 누락됐는가?";

export function questionFor(labelIndex: number | null): string {
  return labelIndex === null ? QUESTION_MISSING : QUESTION_EXISTING;
}

export type BlindCandidate = {
  canonical_candidate_id: string;
  image: string;
  label_index: number | null;
  box: number[] | null;
  // 무엇을 보는 작업인지. **가림 대상이 아니다** — 가리는 것은 방법·점수·
  // 원래 순위·세부 의심 유형이다(docs/manual-timing-pilot.md).
  class_name?: string | null;
  verdict: EvalVerdict | null;
  unique_error_id: string | null;
  /**
   * 묶음 표시 계획이 있는 묶음에서만 온다 — `bundles`의 자리(0부터). 층과 목록 안 위치로만 정해지므로
   * 방법·점수·출처·표본 여부를 드러내지 않는다(사전 등록 D5·D6, 개정 5).
   */
  bundle?: number | null;
};

/** 서버가 주는 묶음 하나. 층과 크기만. */
export type BlindBundle = {
  index: number;
  layer: string;
  /** 그 층 안에서 몇 번째 묶음인가(1부터). */
  layer_bundle: number;
  /** 그 층의 묶음 수. */
  layer_bundles: number;
  size: number;
};

/** 목록 위의 묶음 구간 `[start, end)`. 목록은 묶음 순서로 와서 묶음마다 이어져 있다. */
export type BundleSpan = BlindBundle & { start: number; end: number };

export const LAYER_LABELLED = "labelled_candidates";
export const LAYER_MISSING = "missing_candidates";

export const BUNDLE_MISMATCH_MESSAGE =
  "묶음 정보가 판정 목록과 맞지 않습니다. 판정을 시작하지 말고 묶음 파일을 확인하세요.";

/**
 * 서버의 묶음 표를 목록 구간으로 바꾼다. 묶음이 없으면 `null`(옛 묶음 — 한 목록).
 *
 * **목록과 하나라도 어긋나면 던진다.** 묶음 크기의 합이 목록 길이와 다르거나, 후보의 `bundle`이 자기
 * 구간과 다르면 어느 후보가 어느 묶음인지 믿을 수 없다 — 화면은 판정을 받지 않는다.
 */
export function bundleSpans(
  candidates: BlindCandidate[],
  bundles: BlindBundle[] | null | undefined,
): BundleSpan[] | null {
  if (!bundles || bundles.length === 0) return null;
  const spans: BundleSpan[] = [];
  let start = 0;
  bundles.forEach((b, i) => {
    if (b.index !== i || b.size < 1) throw new Error(BUNDLE_MISMATCH_MESSAGE);
    spans.push({ ...b, start, end: start + b.size });
    start += b.size;
  });
  if (start !== candidates.length) throw new Error(BUNDLE_MISMATCH_MESSAGE);
  for (const span of spans) {
    for (let i = span.start; i < span.end; i += 1) {
      const c = candidates[i];
      const layerOk = span.layer === LAYER_MISSING ? c.label_index === null : c.label_index !== null;
      if (c.bundle !== span.index || !layerOk) throw new Error(BUNDLE_MISMATCH_MESSAGE);
    }
  }
  return spans;
}

/** 목록 자리 `index`가 든 묶음. 묶음이 없거나 범위 밖이면 `null`. */
export function spanAt(spans: BundleSpan[] | null, index: number | null): BundleSpan | null {
  if (!spans || index === null) return null;
  return spans.find((s) => index >= s.start && index < s.end) ?? null;
}

/** "기존 라벨 묶음 2/4" · "누락 묶음". 그 층에 묶음이 하나면 번호를 붙이지 않는다. */
export function bundleLabel(span: BlindBundle): string {
  const name = span.layer === LAYER_MISSING ? "누락 묶음" : "기존 라벨 묶음";
  return span.layer_bundles > 1 ? `${name} ${span.layer_bundle}/${span.layer_bundles}` : name;
}

/** 머리글 — "기존 라벨 묶음 2/4 · 37/96". 위치는 묶음 안의 몇 번째인지일 뿐 원래 순위가 아니다. */
export function bundleHeader(span: BundleSpan, index: number): string {
  return `${bundleLabel(span)} · ${index - span.start + 1}/${span.size}`;
}

const isUnjudged = (judgements: Judgements, c: BlindCandidate) =>
  judgements[c.canonical_candidate_id]?.verdict == null;

/** 묶음 안에서 판정한 수. 진행 상황이지 판정 결과 요약이 아니다. */
export function judgedInSpan(
  candidates: BlindCandidate[],
  judgements: Judgements,
  span: BundleSpan,
): number {
  let n = 0;
  for (let i = span.start; i < span.end; i += 1) if (!isUnjudged(judgements, candidates[i])) n += 1;
  return n;
}

/** 묶음 안에서 `from` 다음의 미판정 — 뒤에 없으면 그 묶음 앞쪽에서 찾는다. 묶음을 넘지 않는다. */
export function nextUnjudgedInSpan(
  candidates: BlindCandidate[],
  judgements: Judgements,
  from: number,
  span: BundleSpan,
): number | null {
  for (let i = from + 1; i < span.end; i += 1) if (isUnjudged(judgements, candidates[i])) return i;
  for (let i = span.start; i <= Math.min(from, span.end - 1); i += 1) {
    if (isUnjudged(judgements, candidates[i])) return i;
  }
  return null;
}

/** 미판정이 남은 가장 앞 묶음. 다 끝났으면 `null`. */
export function firstIncompleteSpan(
  candidates: BlindCandidate[],
  judgements: Judgements,
  spans: BundleSpan[],
): BundleSpan | null {
  return spans.find((s) => judgedInSpan(candidates, judgements, s) < s.size) ?? null;
}

/**
 * 다시 열 때 띄울 자리.
 *
 * **규칙: 미판정이 남은 가장 앞 묶음의 첫 미판정 후보.** 목록이 묶음 순서라 묶음이 있어도 없어도 "목록의
 * 첫 미판정"과 같은 자리다. 묶음 완료 화면에서 창을 닫았다면 다음 묶음의 첫 후보에서 바로 이어진다
 * (완료 화면을 다시 띄우지 않는다). 전부 판정했으면 `null`(완료 화면).
 */
export function resumeIndex(
  candidates: BlindCandidate[],
  judgements: Judgements,
  spans: BundleSpan[] | null,
): number | null {
  if (!spans) return firstUnjudgedIndex(candidates, judgements);
  const span = firstIncompleteSpan(candidates, judgements, spans);
  return span === null ? null : nextUnjudgedInSpan(candidates, judgements, span.start - 1, span);
}

export type AdvanceTarget =
  | { kind: "candidate"; index: number }
  | { kind: "bundle_complete"; bundle: number }
  | { kind: "done" };

/**
 * 저장이 성공한 뒤 어디로 가는가.
 *
 * - 묶음이 없으면 예전 그대로 — 다음 미판정(뒤에 없으면 앞), 없으면 완료.
 * - 묶음이 있으면 **그 묶음 안에서만** 다음 미판정을 찾는다. 묶음이 다 찼으면 묶음 완료 화면, 전부
 *   끝났으면 완료 화면. 다음 묶음으로는 판정자가 "다음 묶음 시작"을 눌러야 간다.
 */
export function advanceTarget(
  candidates: BlindCandidate[],
  judgements: Judgements,
  from: number,
  spans: BundleSpan[] | null,
): AdvanceTarget {
  if (!spans) {
    const index = nextUnjudgedIndex(candidates, judgements, from);
    return index === null ? { kind: "done" } : { kind: "candidate", index };
  }
  const span = spanAt(spans, from);
  const index = span ? nextUnjudgedInSpan(candidates, judgements, from, span) : null;
  if (index !== null) return { kind: "candidate", index };
  if (unjudgedCount(candidates, judgements) === 0) return { kind: "done" };
  return { kind: "bundle_complete", bundle: span ? span.index : 0 };
}

/** 묶음 완료 화면 문구. 쉬어도 된다는 것만 말하고 판정 결과는 말하지 않는다. */
export function bundleCompleteMessage(span: BlindBundle): string {
  return `${bundleLabel(span)} 판정을 마쳤습니다 (${span.size}건). 여기서 쉬어도 됩니다 — 판정은 이미 ` +
    "저장되어 있어 창을 닫았다가 다시 열어도 다음 묶음의 첫 미판정 후보에서 이어집니다.";
}

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
        // **순차 실행이 이 함수의 목적이다.** 병렬로 보내면 순서가 뒤집혀
        // 옛 판정이 최종본이 된다.
        //
        // `no-await-in-loop`는 `.oxlintrc.json`의 overrides에서 이 파일만
        // 끈다 — 전역 규칙은 켜 둔다.
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

export type SaveState = "saving" | "saved" | "advanced" | "failed" | "idle";

/**
 * 저장 상태 문구. 실패를 조용히 넘기지 않는다.
 *
 * `advanced`는 **앞 후보의 판정이 저장돼서 이 후보로 넘어왔다**는 뜻이다. "저장됨"을 그대로 두면
 * 아직 판정하지 않은 지금 후보가 저장된 것처럼 읽힌다.
 */
export function saveMessage(state: SaveState): string {
  if (state === "saving") return "저장 중…";
  if (state === "saved") return "저장됨";
  if (state === "advanced") return "앞 후보 저장됨 — 다음 후보로 넘어왔습니다";
  if (state === "failed") return "저장 실패 — 저장하지 못했습니다. 다시 시도를 누르세요.";
  return "";
}

/**
 * 아직 판정하지 않은 첫 후보의 자리. 전부 판정했으면 `null`.
 *
 * **두 번째 세션이 0번부터 시작하면 안 된다.** 이미 판정한 후보를 넘기는
 * 시간이 그 후보들의 판정 시간에 다시 쌓여, 후보당 시간이 부풀고 N이 작아진다.
 * (docs/pilot-evaluation-plan.md)
 */
export function firstUnjudgedIndex(
  candidates: BlindCandidate[],
  judgements: Judgements,
): number | null {
  const at = candidates.findIndex(
    (c) => judgements[c.canonical_candidate_id]?.verdict == null,
  );
  return at === -1 ? null : at;
}

/**
 * `from` 다음의 미판정 후보. 뒤에 없으면 앞에서 찾는다. 전부 판정했으면 `null`.
 *
 * 앞으로 감싸 도는 이유는 **건너뛴 후보를 되찾기 위해서다** — 보류로 미뤄 두고
 * 넘어간 것이 앞쪽에 남아 있을 수 있다.
 */
export function nextUnjudgedIndex(
  candidates: BlindCandidate[],
  judgements: Judgements,
  from: number,
): number | null {
  const unjudged = (c: BlindCandidate) =>
    judgements[c.canonical_candidate_id]?.verdict == null;

  const ahead = candidates.findIndex((c, i) => i > from && unjudged(c));
  if (ahead !== -1) return ahead;
  const behind = candidates.findIndex((c, i) => i <= from && unjudged(c));
  return behind === -1 ? null : behind;
}

/** 남은 미판정 후보 수. 완료 화면을 보일지 정하는 데 쓴다. */
export function unjudgedCount(
  candidates: BlindCandidate[],
  judgements: Judgements,
): number {
  return candidates.filter(
    (c) => judgements[c.canonical_candidate_id]?.verdict == null,
  ).length;
}

export const ALL_JUDGED_MESSAGE =
  "이 묶음의 후보를 모두 판정했습니다. 다시 볼 것이 없으면 창을 닫으세요.";
