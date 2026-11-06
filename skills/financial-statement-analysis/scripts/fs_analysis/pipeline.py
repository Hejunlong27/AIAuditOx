"""编排：加载 -> 校验 -> 分析 -> 输出。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import analysis, reports
from .analysis import AnalysisResult
from .loader import ReportSet, load_workbook
from . import config as cfg


def build_chart_data(report: ReportSet) -> dict:
    def triple(statement, item):
        cur, prior = report.get(statement, item)
        return (item, prior, cur)

    income = [
        triple("利润表", "营业收入"),
        triple("利润表", "营业成本"),
        triple("利润表", "净利润"),
    ]
    balance = [
        triple("资产负债表", "资产总计"),
        triple("资产负债表", "负债合计"),
        triple("资产负债表", "所有者权益合计"),
        triple("资产负债表", "货币资金"),
        triple("资产负债表", "应收账款"),
        triple("资产负债表", "存货"),
    ]
    return {
        "income": [t for t in income if t[1] is not None or t[2] is not None],
        "balance": [t for t in balance if t[1] is not None or t[2] is not None],
    }


def analyze(
    input_path: str | Path,
    entity: str | None = None,
    period: str | None = None,
    materiality: float | None = None,
) -> tuple[ReportSet, AnalysisResult]:
    report = load_workbook(input_path)

    materiality_source = "由使用人提供"
    suggestion = analysis.suggest_materiality(report)
    if materiality is None:
        materiality = suggestion["suggestion"]
        materiality_source = (
            f"未提供，程序按{'、'.join(suggestion['basis_used'])}测算的建议值，待人工确认"
            if materiality else "未提供且无法测算，全部阈值比较仅供参考"
        )

    result = AnalysisResult()
    result.meta = {
        "entity": entity,
        "period": period,
        "input": str(input_path),
        "run_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "materiality": materiality,
        "materiality_source": materiality_source,
        "version": cfg.VERSION,
        "suggestion": suggestion,
    }
    result.validation = analysis.validate(report, materiality)
    result.structure = analysis.structure(report, materiality)
    result.trend = analysis.trend(report, materiality)
    result.ratios = analysis.compute_ratios(report)
    result.expectation = analysis.expectation(report, materiality)
    ratio_map = {row["指标"]: row for row in result.ratios}
    result.consistency = analysis.consistency(report, materiality, ratio_map)
    result.exceptions = analysis.build_exceptions(result)
    result.unmapped = report.all_unmapped
    result.warnings = list(report.warnings)
    result.meta["chart_data"] = build_chart_data(report)
    return report, result


def run(
    input_path: str | Path,
    outdir: str | Path = "output",
    entity: str | None = None,
    period: str | None = None,
    materiality: float | None = None,
    stem: str | None = None,
) -> dict:
    report, result = analyze(input_path, entity=entity, period=period, materiality=materiality)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = stem or Path(input_path).stem
    prefix = f"{stem}-分析程序"

    paths = {
        "excel": reports.write_excel(result, outdir / f"{prefix}.xlsx"),
        "word": reports.write_word(result, outdir / f"{prefix}-分析底稿.docx"),
        "csv": reports.write_exception_csv(result, outdir / f"{prefix}-异常清单.csv"),
        "log": reports.write_log(result, outdir / f"{prefix}-运行日志.txt"),
    }
    paths["revision"] = reports.write_revision_log(
        result, outdir / f"{prefix}-修订记录.md", f"{prefix}"
    )
    return {"paths": paths, "result": result, "report": report}
