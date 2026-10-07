/**
 * 첫 방문 튜토리얼을 봤는지 기억한다. 저장소가 막혀 있으면(사생활 모드 등) 첫 방문으로 보고 띄우고,
 * 닫은 것은 그 화면이 떠 있는 동안만 기억한다.
 */
export const TUTORIAL_KEY = "aida-blind-tutorial-v2";

export function tutorialSeen(): boolean {
  try {
    return localStorage.getItem(TUTORIAL_KEY) === "done";
  } catch {
    return false;
  }
}

export function rememberTutorial(): void {
  try {
    localStorage.setItem(TUTORIAL_KEY, "done");
  } catch {
    // 기억하지 못해도 화면은 이어진다 — 다음 방문에 다시 뜰 뿐이다.
  }
}
