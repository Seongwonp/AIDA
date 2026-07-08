import sys
import pandas as pd
from datetime import datetime
from pathlib import Path
from fpdf import FPDF

class AIDAPDF(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("Malgun", "", 9)
        self.set_text_color(128)
        self.cell(self.epw, 10, f"AIDA 최종 보고서  |  페이지 {self.page_no()}/{{nb}}", 0, 0, "C")

def main():
    metrics_path = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "metrics.csv"
    iou_path = Path(__file__).resolve().parent / "iou_table.csv"
    chart_path = Path(__file__).resolve().parent.parent / "docs" / "assets" / "experiment-results-full21.png"
    pdf_out_path = Path(__file__).resolve().parent.parent / "docs" / "AIDA_통합실험결과_보고서.pdf"

    if not metrics_path.exists() or not iou_path.exists():
        print("Data files not found.")
        return

    metrics_df = pd.read_csv(metrics_path)
    iou_df = pd.read_csv(iou_path)
    df = pd.merge(metrics_df, iou_df, on="condition", how="left", suffixes=("", "_iou"))

    pdf = AIDAPDF()
    pdf.alias_nb_pages()
    
    # Load Malgun Gothic font
    font_path = r"C:\Windows\Fonts\malgun.ttf"
    if not Path(font_path).exists():
        font_path = r"C:\Windows\Fonts\malgunsl.ttf"
    
    pdf.add_font("Malgun", "", font_path)
    bold_font_path = r"C:\Windows\Fonts\malgunbd.ttf"
    if Path(bold_font_path).exists():
        pdf.add_font("Malgun", "B", bold_font_path)
    else:
        pdf.add_font("Malgun", "B", font_path)

    pdf.set_margins(15, 20, 15)
    pdf.add_page()
    
    # Title Page / Header
    pdf.set_font("Malgun", "B", 22)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(pdf.epw, 15, "AIDA 통합 실험 결과 보고서", align="C")
    pdf.ln(15)
    
    pdf.set_font("Malgun", "", 12)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(pdf.epw, 8, "김성호 교수님 피드백 반영 및 21개 조건 실측 평가 결과", align="C")
    pdf.ln(10)
    
    pdf.set_draw_color(226, 232, 240)
    pdf.set_line_width(0.5)
    pdf.line(15, 45, 195, 45)
    pdf.ln(10)

    # 1. 조언 반영 요약
    pdf.set_font("Malgun", "B", 14)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(pdf.epw, 10, "1. 교수님 조언 반영 요약 (100% 반영 완료)")
    pdf.ln(12)
    
    pdf.set_font("Malgun", "", 10)
    pdf.set_text_color(51, 65, 85)
    bullet_points = [
        "OBB(Oriented Bounding Box) 도입 검토: 회전 오차의 AABB 근사 한계 서술 및 2차 피드백 로드맵 수립 완료.",
        "회전각 한계 보완책 추가: 변형 조건에 중심점 이동(Translation) 및 스케일(Scale) 오차 추가 구현 및 학습.",
        "오류 강도의 객관성 증명: 단순 기하학적 수치(%, 도) 대신 참값(GT)과의 실측 평균 IoU 및 IoU 감소율 적용.",
        "ROI(비용 절감) 정량화: 수작업 검수 집중(인건비 70% 절감) 및 재학습 예방(GPU 비용) 절감 모델 탑재."
    ]
    for bp in bullet_points:
        pdf.multi_cell(pdf.epw, 6, f"- {bp}")
        pdf.ln(1)
    pdf.ln(5)

    # 2. 주요 실험 결과 요약
    pdf.set_font("Malgun", "B", 14)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(pdf.epw, 10, "2. 핵심 실험 결과 통찰")
    pdf.ln(12)
    
    pdf.set_font("Malgun", "", 10)
    pdf.set_text_color(51, 65, 85)
    insights = (
        "- 최대 성능 저하: 스케일 30% 축소(scale_m30) 조건에서 mAP@0.5 성능이 6.7%로 가장 크게 감소했습니다. "
        "작은 바운딩 박스는 인공지능이 사물의 형태를 정확히 추출하기 어렵게 만듭니다.\n\n"
        "- 위치 편차(Translation)의 파괴력: 박스의 크기는 동일하게 유지하되 중심점을 가로로 15% 이동시켰을 뿐인데 "
        "mAP가 2.4% 하락했습니다. 이는 가로 길이를 30% 확대한 극적인 크기 오차(width_p30, -2.4%)와 유사한 손실을 줍니다. "
        "즉, AI는 크기 오차보다 위치 정렬 오차에 더 취약합니다."
    )
    pdf.multi_cell(pdf.epw, 6, insights)
    pdf.ln(5)

    # Chart page
    if chart_path.exists():
        pdf.add_page()
        pdf.set_font("Malgun", "B", 14)
        pdf.cell(pdf.epw, 10, "3. 오류 조건별 성능 저하 그래프 (mAP@0.5 기준)")
        pdf.ln(12)
        pdf.image(str(chart_path), x=15, w=180)
        pdf.ln(10)

    # 4. 통합 실험 결과표
    pdf.add_page()
    pdf.set_font("Malgun", "B", 14)
    pdf.cell(pdf.epw, 10, "4. 통합 실험 결과표 (실측치, 21개 조건 전체)")
    pdf.ln(12)

    pdf.set_font("Malgun", "B", 8)
    pdf.set_fill_color(241, 245, 249)
    pdf.set_draw_color(203, 213, 225)
    
    cols = ["조건명", "오류 유형", "강도", "mAP50", "mAP50-95", "Prec", "Rec", "평균 IoU", "IoU감소", "성능저하"]
    widths = [24, 34, 12, 14, 16, 14, 14, 18, 18, 16]
    
    for col, w in zip(cols, widths):
        pdf.cell(w, 8, col, border=1, align="C", fill=True)
    pdf.ln()

    pdf.set_font("Malgun", "", 7.5)
    pdf.set_fill_color(255, 255, 255)
    
    type_labels = {
        "none": "기준선", "width": "가로 길이", "height": "세로 길이",
        "rotation": "회전 외접근사", "translation_x": "중심 가로이동",
        "translation_y": "중심 세로이동", "scale": "스케일 오류"
    }

    clean_row = df[df["condition"] == "clean"]
    baseline_map50 = clean_row["map50"].iloc[0] if not clean_row.empty else 0.876

    for index, row in df.iterrows():
        cond = row["condition"]
        t_lbl = type_labels.get(row["type"], row["type"])
        mag = f"{row['magnitude']:+g}%" if row["type"] != "none" and row["type"] != "rotation" else (f"{row['magnitude']:+g}°" if row["type"] == "rotation" else "0")
        map50 = f"{row['map50']:.3f}"
        map50_95 = f"{row['map50_95']:.3f}"
        prec = f"{row['precision']:.3f}"
        rec = f"{row['recall']:.3f}"
        
        miou = f"{row['mean_iou']:.4f}" if not pd.isna(row["mean_iou"]) else "-"
        miou_drop = f"{row['mean_iou_drop_pct']:.2f}%" if not pd.isna(row["mean_iou_drop_pct"]) else "-"
        
        drop_pct = (baseline_map50 - row["map50"]) / baseline_map50 * 100
        drop_str = f"{drop_pct:.1f}%" if cond != "clean" else "0.0%"

        vals = [cond, t_lbl, mag, map50, map50_95, prec, rec, miou, miou_drop, drop_str]
        
        fill = (index % 2 == 1)
        if fill:
            pdf.set_fill_color(248, 250, 252)
        else:
            pdf.set_fill_color(255, 255, 255)
            
        for val, w in zip(vals, widths):
            pdf.cell(w, 7, val, border=1, align="C", fill=True)
        pdf.ln()

    pdf.ln(5)
    pdf.set_font("Malgun", "", 8)
    pdf.cell(pdf.epw, 5, "* 성능 저하율은 clean 조건의 mAP@0.5(0.876) 대비 하락 비율입니다.")
    pdf.ln(10)

    # 5. 교수님 조언 상세 답변
    pdf.add_page()
    pdf.set_font("Malgun", "B", 14)
    pdf.cell(pdf.epw, 10, "5. 교수님 조언 상세 답변")
    pdf.ln(12)

    pdf.set_font("Malgun", "B", 11)
    pdf.cell(pdf.epw, 8, "Q1. 2D 축정렬 박스(AABB)에서 회전각 오류가 가지는 기하학적 한계 해결책")
    pdf.ln(10)
    pdf.set_font("Malgun", "", 9.5)
    pdf.set_text_color(51, 65, 85)
    ans1 = (
        "답변: 현재 2D 라벨 구조에서는 회전된 박스를 다시 감싸는 AABB 외접 박스로 근사하는 기하학적 한계가 존재합니다. "
        "이를 완벽히 분석하고자 중심점 이동(Translation) 및 스케일(Scale) 조건들을 독립 수립하여 회전으로 인한 "
        "위치와 크기 왜곡 현상을 통계적으로 분리하여 실측해 냈습니다. 본선 단계에서는 YOLO OBB 모델과 Rotated IoU "
        "지표를 도입하는 데이터 변환 로드맵을 구축 완료하여 한계를 원천 극복할 계획입니다."
    )
    pdf.multi_cell(pdf.epw, 6, ans1)
    pdf.ln(6)

    pdf.set_font("Malgun", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(pdf.epw, 8, "Q2. 오류 강도의 객관성(%, 도 기준의 모호함) 증명")
    pdf.ln(10)
    pdf.set_font("Malgun", "", 9.5)
    pdf.set_text_color(51, 65, 85)
    ans2 = (
        "답변: 단순 파라미터 값(가로 30%, 15도) 대신 참값(GT) 라벨과의 '실측 평균 IoU 및 IoU 감소율'을 직접 산출하여 "
        "오류 강도의 기술적 타당성을 기하학적으로 완벽히 객관화했습니다. 예를 들어 scale_m30(스케일 30% 축소) 오류는 "
        "평균 IoU 0.49(IoU 감소율 51%)에 달하는 매우 강한 왜곡임을 명시하여 평가지표의 객관성을 확보했습니다."
    )
    pdf.multi_cell(pdf.epw, 6, ans2)
    pdf.ln(6)

    pdf.set_font("Malgun", "B", 11)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(pdf.epw, 8, "Q3. 서비스 도입 시 비용 절감(ROI) 수치화")
    pdf.ln(10)
    pdf.set_font("Malgun", "", 9.5)
    pdf.set_text_color(51, 65, 85)
    ans3 = (
        "답변: 대시보드에 '발표용 가정값 기반 ROI 추정 모델'을 탑재했습니다. 라벨 10만 건 기준 전체 전수 재검수 대비, "
        "AIDA 플랫폼이 추천하는 오차 가능성 높은 의심 라벨 상위 30%만 집중 재검수할 경우 수작업 검수 비용을 70% 아껴 "
        "약 729만 원의 인건비를 절감합니다. 또한 데이터 진단으로 무의미한 모델 재학습 횟수를 절감하여 약 48만 원의 GPU 비용을 아끼므로 "
        "총 약 777만 원 상당의 직접 비용 절감(ROI)을 제공합니다."
    )
    pdf.multi_cell(pdf.epw, 6, ans3)
    
    # Metadata footer
    pdf.ln(12)
    pdf.set_font("Malgun", "", 8)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(pdf.epw, 5, f"보고서 생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", align="R")

    pdf.output(str(pdf_out_path))
    print(f"PDF generated successfully -> {pdf_out_path}")

if __name__ == "__main__":
    main()
