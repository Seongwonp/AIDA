import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// 검사 설정을 vite.config.ts와 갈라 둔다 — 거기 `test` 필드를 넣으면
// `tsc -b`가 vite 타입에 없는 속성이라며 막는다.
export default defineConfig({
  plugins: [react()],
  test: {
    // 순수 로직 검사만 있을 때는 환경이 필요 없었다. R1부터는 **실제 React
    // 화면**의 비동기 흐름을 재현해야 해서 DOM이 필요하다 (docs/25 R1).
    //
    // 순수 함수만 부르는 검사로 대체하지 않는다 — 지금 의심하는 결함이
    // 컴포넌트의 상태 갱신 순서에 있기 때문이다.
    environment: 'jsdom',
  },
})
