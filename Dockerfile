# AIDA 시연용 이미지 — 프론트를 빌드해 백엔드가 같이 서빙한다.
#
# **추론은 안 된다.** 진단은 experiment/venv에서 ultralytics·torch로 도는
# 서브프로세스인데, 그건 GPU가 필요하고 이미지에 넣으면 몇 GB가 된다. 여기
# 담기는 것은 CSV·JSON만 읽는 쪽이다.
#
# 그래서 되는 것:
#   - 연구 결과 화면 (조건별 지표, ROI, OBB 비교, 방법론)
#   - 지난 진단 열어보기 — 이미 만들어 둔 결과를 읽는 것이므로 GPU가 필요 없다
#   - 재검수 목록·판정·CSV 내려받기
# 안 되는 것:
#   - 새 zip을 올려 진단하기 (POST .../diagnose, .../diagnose-labels → 500)
#
# 그 구분은 docs/04-api-reference.md의 "무엇이 GPU를 쓰는가" 표와 같다.

FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# 같은 오리진에서 서빙하므로 API 주소를 비운다 — 상대 경로로 나간다
ENV VITE_API_BASE_URL=""
RUN npm run build


FROM python:3.14-slim
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=web /web/dist ./static

# 실험 산출물 중 백엔드가 읽는 CSV만 넣는다. runs*(가중치)와 conditions*
# (이미지)는 수십 GB라 안 넣는다 — 어차피 추론을 못 한다.
COPY experiment/reliability_profile_*.json ./experiment/

ENV UPLOADS_DIR=/data/uploads \
    EXPERIMENT_ROOT=/app/experiment \
    CORS_ORIGINS=""
VOLUME ["/data"]
EXPOSE 8000

# 헬스체크는 CSV만 읽는 경로로 — GPU가 없어도 200이어야 한다
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
