/**
 * 업로드 진단에서 **외부 자를 고르는 길**이 있는가 (사전 등록 D1).
 *
 * 결과 화면이 아니라 서버에 무엇을 보냈는지만 본다 — 고른 자가 아닌 자로
 * 재는 것이 여기서 생길 수 있는 사고다.
 */
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const diagnoseDatasetLabels = vi.fn();
const listRulers = vi.fn();
vi.mock("../api", () => ({
  uploadDataset: () =>
    Promise.resolve({
      dataset_id: "0123456789ab", uploaded_at: "2026-09-16T00:00:00",
      num_images: 1, num_labels: 1, label_class_ids: [0],
      suggested_profile: "kitti", suggestion_reason: "이유",
    }),
  // 결과 표는 이 검사의 관심사가 아니므로 진단은 실패시켜 둔다.
  diagnoseDataset: () => Promise.reject(new Error("stop")),
  diagnoseDatasetLabels: (...a: unknown[]) => {
    diagnoseDatasetLabels(...a);
    return Promise.reject(new Error("stop"));
  },
  getLabelDiagnosis: () => Promise.reject(new Error("stop")),
  getDatasetReportUrl: () => "",
  getReliabilityProfiles: () => Promise.resolve([]),
  getDatasetHistory: () => Promise.resolve([]),
  deleteDataset: () => Promise.resolve(),
  listRulers: () => listRulers(),
}));

import { DatasetUpload } from "./DatasetUpload";

afterEach(() => {
  cleanup();
  diagnoseDatasetLabels.mockClear();
});

const RULERS = [
  {
    ruler_id: "nuimages_car_v1_e100",
    label: "nuImages Car 자",
    classes: ["Car"],
    dataset: "nuimages",
    weights_path: "runs_nuimages/car_v1_e100/weights/best.pt",
    available: true,
    weights_sha256: "abc",
  },
];

const pickFile = () => {
  const input = document.getElementById("dataset-zip-input") as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["x"], "d.zip")] } });
};

test("자를 고르면 그 ruler_id를 보내고 프로파일은 섞지 않는다", async () => {
  listRulers.mockResolvedValue(RULERS);
  render(<DatasetUpload />);

  const select = (await screen.findByLabelText("기준 모델(자) 선택")) as HTMLSelectElement;
  expect(select.value).toBe("");           // 기본은 내장 자
  fireEvent.change(select, { target: { value: "nuimages_car_v1_e100" } });
  pickFile();
  fireEvent.click(screen.getByRole("button", { name: "업로드 & 진단" }));

  await waitFor(() => expect(diagnoseDatasetLabels).toHaveBeenCalled());
  expect(diagnoseDatasetLabels).toHaveBeenCalledWith(
    "0123456789ab", "", "aida_v1_systematic_boost", "nuimages_car_v1_e100");
});

test("고르지 않으면 자를 보내지 않고 추천 프로파일로 돈다", async () => {
  listRulers.mockResolvedValue(RULERS);
  render(<DatasetUpload />);

  await screen.findByLabelText("기준 모델(자) 선택");
  pickFile();
  fireEvent.click(screen.getByRole("button", { name: "업로드 & 진단" }));

  await waitFor(() => expect(diagnoseDatasetLabels).toHaveBeenCalled());
  expect(diagnoseDatasetLabels).toHaveBeenCalledWith(
    "0123456789ab", "kitti", "aida_v1_systematic_boost", "");
});

test("목록을 못 불러오면 선택 칸 없이 기본 자로 돈다", async () => {
  listRulers.mockRejectedValue(new Error("no"));
  render(<DatasetUpload />);

  await waitFor(() => expect(listRulers).toHaveBeenCalled());
  expect(screen.queryByLabelText("기준 모델(자) 선택")).toBeNull();
});
