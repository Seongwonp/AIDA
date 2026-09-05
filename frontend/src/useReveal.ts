import { useEffect } from "react";

/**
 * 스크롤해서 화면에 들어온 요소를 나타나게 한다 (AOS 같은 것).
 *
 * 라이브러리를 안 쓴다. AOS는 15KB 남짓인데 하는 일이 IntersectionObserver
 * 한 번 감기는 것이라, 의존성을 늘릴 값어치가 없다.
 *
 * `data-reveal` 속성이 붙은 요소를 찾아 화면에 들어오면 `is-revealed`를
 * 붙인다. 한 번 나타난 것은 다시 감추지 않는다 — 위아래로 스크롤할 때마다
 * 깜빡이면 읽는 걸 방해한다.
 *
 * 움직임을 싫어하는 설정이면 관찰을 시작하지도 않고 전부 바로 보이게 한다.
 * 애니메이션을 CSS에만 맡기면 그 설정에서 요소가 영영 투명한 채로 남는다.
 */
export function useReveal(deps: unknown[] = []) {
  useEffect(() => {
    const targets = document.querySelectorAll<HTMLElement>("[data-reveal]");
    if (!targets.length) return;

    // 스크립트가 살아 있을 때만 감춘다. CSS에만 맡기면 자바스크립트가
    // 실패했을 때 내용이 영영 투명하게 남는다.
    document.documentElement.classList.add("js-reveal");

    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !("IntersectionObserver" in window)) {
      targets.forEach((el) => el.classList.add("is-revealed"));
      return;
    }

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (!e.isIntersecting) return;
          const el = e.target as HTMLElement;
          // 형제끼리 조금씩 늦춰 차례로 올라오게 한다. 한꺼번에 나타나면
          // 움직임이 뭉쳐 보인다.
          const delay = Number(el.dataset.revealDelay ?? 0);
          window.setTimeout(() => el.classList.add("is-revealed"), delay);
          io.unobserve(el);          // 한 번 나타나면 그만 본다
        });
      },
      // 아래에서 15% 정도 올라왔을 때 시작한다 — 화면에 완전히 들어온
      // 뒤에 움직이면 이미 읽고 있던 것이 흔들린다.
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" },
    );

    targets.forEach((el) => io.observe(el));

    // 안전망. 관찰 콜백이 오지 않는 환경이 실제로 있다 — 이 프로젝트의
    // 미리보기 브라우저에서 스크롤은 되는데 IntersectionObserver가 한 번도
    // 안 불렸다. 그런 곳에서는 내용이 영영 투명하게 남는다.
    //
    // 효과보다 읽히는 게 먼저다. 시간이 지나면 남은 것을 그냥 보여준다.
    const failsafe = window.setTimeout(() => {
      targets.forEach((el) => el.classList.add("is-revealed"));
    }, 2500);

    return () => {
      io.disconnect();
      window.clearTimeout(failsafe);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
