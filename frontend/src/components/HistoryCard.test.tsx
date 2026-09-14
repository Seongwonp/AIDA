/**
 * 지난 진단 목록이 **어느 순위 버전의 결과인지** 보여 주고 그 버전으로 여는가
 * (docs/adr-ranking-separation.md).
 */
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const getDatasetHistory = vi.fn();
vi.mock("../api", () => ({
  getDatasetHistory: (...a: unknown[]) => getDatasetHistory(...a),
  deleteDataset: () => Promise.resolve(),
}));

import { HistoryCard } from "./HistoryCard";

afterEach(cleanup);

const row = (versions?: string[]) => ({
  dataset_id: "0123456789ab",
  diagnosed_at: "2026-09-14T00:00:00",
  num_images: 3,
  num_labels: 5,
  has_label_diagnosis: true,
  total_findings: 2,
  dominant_label: "가로 길이 어긋남",
  ...(versions ? { ranking_versions: versions } : {}),
});

test("버전마다 열기 버튼이 있고 고른 버전으로 연다", async () => {
  getDatasetHistory.mockResolvedValue([row(["aida_v1_systematic_boost", "aida_v2_candidate_iou"])]);
  const onOpen = vi.fn();
  render(<HistoryCard onOpen={onOpen} />);

  fireEvent.click(await screen.findByRole("button", { name: "열기 · v2" }));
  expect(onOpen).toHaveBeenCalledWith("0123456789ab", "aida_v2_candidate_iou");

  fireEvent.click(screen.getByRole("button", { name: "열기 · v1" }));
  expect(onOpen).toHaveBeenLastCalledWith("0123456789ab", "aida_v1_systematic_boost");
});

test("버전 기록을 모르는 옛 응답은 v1 하나로 연다", async () => {
  getDatasetHistory.mockResolvedValue([row()]);
  const onOpen = vi.fn();
  render(<HistoryCard onOpen={onOpen} />);

  fireEvent.click(await screen.findByRole("button", { name: "열기 · v1" }));
  expect(onOpen).toHaveBeenCalledWith("0123456789ab", "aida_v1_systematic_boost");
  expect(screen.queryByRole("button", { name: "열기 · v2" })).toBeNull();
});
