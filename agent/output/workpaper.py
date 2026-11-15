"""Deterministic workpaper generation for executable audit plans."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from agent.models.artifact import ArtifactRecord
from agent.models.evidence import Evidence
from agent.models.plan import AuditPlan
from agent.models.project import AuditProject
from agent.models.task import AuditTask
from agent.security.workspace import Workspace, sha256_file

_THIN = Side(style="thin", color="A6A6A6")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEADER_FILL = PatternFill("solid", fgColor="D9EAF7")
_SECTION_FILL = PatternFill("solid", fgColor="1F4E78")
_WARNING_FILL = PatternFill("solid", fgColor="FFF2CC")
_SUCCESS_FILL = PatternFill("solid", fgColor="E2F0D9")
_DANGER_FILL = PatternFill("solid", fgColor="FCE4D6")


STATUS_LABELS = {
    "PENDING": "待执行",
    "BLOCKED": "缺少输入",
    "READY": "可执行",
    "RUNNING": "执行中",
    "WAITING_HUMAN": "等待人工",
    "HUMAN_COMPLETED": "人工材料已提交",
    "VERIFYING": "质量检查中",
    "VERIFIED": "已通过",
    "SKIPPED_NOT_APPLICABLE": "条件不适用",
    "FAILED": "失败",
}


class WorkpaperWriter:
    """Write a human-reviewable execution workpaper without inventing results."""

    def write_bank_deposits(
        self,
        *,
        workspace: Workspace,
        project: AuditProject,
        task: AuditTask,
        plan: AuditPlan,
        evidence: list[Evidence],
        prepared_by: str,
        reviewer: str = "",
    ) -> ArtifactRecord:
        stem = "Z-1-2_银行存款审计执行底稿"
        target = workspace.resolve_for_write(workspace.workpaper_dir / f"{stem}.xlsx")
        preview = workspace.resolve_for_write(f"{workspace.workpaper_dir / stem}.md")
        if target.exists():
            workspace.backup(target)
        if preview.exists():
            workspace.backup(preview)

        wb = Workbook()
        main = wb.active
        main.title = "工作底稿"
        self._write_main_sheet(main, project, task, plan, evidence, prepared_by, reviewer)
        details = wb.create_sheet("程序明细")
        self._write_procedure_sheet(details, plan)
        evidence_sheet = wb.create_sheet("证据清单")
        self._write_evidence_sheet(evidence_sheet, evidence)
        revision = wb.create_sheet("修订记录")
        self._write_revision_sheet(revision, task, prepared_by, reviewer)
        wb.properties.creator = "审小牛 AIAuditOx"
        wb.properties.title = stem
        wb.properties.subject = "审计程序执行底稿"
        wb.save(target)

        preview.write_text(
            self._render_markdown(project, task, plan, evidence, prepared_by, reviewer),
            encoding="utf-8",
        )
        digest = sha256_file(target)
        return ArtifactRecord(
            artifact_id=f"ART-{uuid4().hex[:12]}",
            task_id=task.task_id,
            kind="WORKPAPER_XLSX",
            path=str(target),
            sha256=digest,
            size_bytes=target.stat().st_size,
            template_version="runtime-four-section-v1",
            metadata={
                "preview_path": str(preview),
                "preview_sha256": sha256_file(preview),
                "index": "Z-1-2-00",
                "status": task.status.value,
            },
        )

    def _write_main_sheet(
        self,
        ws,
        project: AuditProject,
        task: AuditTask,
        plan: AuditPlan,
        evidence: list[Evidence],
        prepared_by: str,
        reviewer: str,
    ) -> None:
        ws.sheet_view.showGridLines = False
        self._widths(ws, [18, 28, 18, 28, 18, 22, 18, 22])
        row = 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
        title = ws.cell(row, 1, "银行存款审计程序执行工作底稿")
        title.font = Font(size=18, bold=True, color="FFFFFF")
        title.fill = _SECTION_FILL
        title.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[row].height = 30
        row += 1

        values = [
            "被审计单位",
            project.client_label or project.name,
            "审计期间",
            project.period or "",
            "索引号",
            "Z-1-2-00",
            "状态",
            STATUS_LABELS.get(task.status.value, task.status.value),
        ]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row, col, value)
            cell.border = _BORDER
            if col % 2 == 1:
                cell.font = Font(bold=True)
                cell.fill = _HEADER_FILL
        row += 1
        second = [
            "编制人",
            prepared_by,
            "编制日期",
            task.created_at.date().isoformat(),
            "审核人",
            reviewer,
            "审核日期",
            "",
        ]
        for col, value in enumerate(second, 1):
            cell = ws.cell(row, col, value)
            cell.border = _BORDER
            if col % 2 == 1:
                cell.font = Font(bold=True)
                cell.fill = _HEADER_FILL
        row += 2

        self._section(ws, row, 8, "一、项目基本信息")
        row += 1
        for label, value in (
            ("项目 ID", project.project_id),
            ("任务 ID", task.task_id),
            ("审计技能", plan.skill_id),
            ("技能版本", plan.skill_version),
            ("用户请求", task.user_request),
        ):
            ws.cell(row, 1, label).font = Font(bold=True)
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=8)
            ws.cell(row, 2, value).alignment = Alignment(wrap_text=True)
            row += 1
        row += 1

        self._section(ws, row, 8, "二、审计目标和程序说明")
        row += 1
        ws.cell(row, 1, "审计目标").font = Font(bold=True)
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=8)
        ws.cell(row, 2, "执行银行存款审计程序，形成可追溯的执行记录；本底稿不构成审计意见。").alignment = Alignment(wrap_text=True)
        row += 1
        headers = ["程序", "程序名称", "执行方式", "依赖", "工具", "底稿索引", "状态"]
        for col, value in enumerate(headers, 1):
            cell = ws.cell(row, col, value)
            cell.font = Font(bold=True)
            cell.fill = _HEADER_FILL
            cell.border = _BORDER
        row += 1
        for step in plan.steps:
            values = [
                step.step_id,
                step.name,
                step.execution_mode.value,
                "、".join(step.dependencies) or "—",
                "、".join(step.required_tools) or "—",
                step.workpaper_index or "—",
                STATUS_LABELS.get(step.status.value, step.status.value),
            ]
            for col, value in enumerate(values, 1):
                cell = ws.cell(row, col, value)
                cell.border = _BORDER
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            self._status_fill(ws.cell(row, 7), step.status.value)
            row += 1
        row += 1

        self._section(ws, row, 8, "三、审计程序执行结果")
        row += 1
        summary = [
            ("活动程序", str(sum(1 for step in plan.steps if step.status.value != "SKIPPED_NOT_APPLICABLE"))),
            ("已通过程序", str(sum(1 for step in plan.steps if step.status.value == "VERIFIED"))),
            ("等待人工程序", str(sum(1 for step in plan.steps if step.status.value == "WAITING_HUMAN"))),
            ("证据数量", str(len(evidence))),
            ("可追溯证据", str(sum(1 for item in evidence if item.traceable))),
        ]
        for label, value in summary:
            ws.cell(row, 1, label).font = Font(bold=True)
            ws.cell(row, 1).fill = _HEADER_FILL
            ws.cell(row, 2, value)
            row += 1
        row += 1
        self._section(ws, row, 8, "四、审计说明")
        row += 1
        notes = [
            "本底稿为运行时执行记录，差异类结论必须由项目组人工确认。",
            "工具结果和人工材料均需保留原始文件及哈希，证据未通过复核前不得关闭程序。",
            "Excel 公式不参与运行时求值；关键金额应由确定性工具或 Python 独立复算。",
        ]
        if plan.warnings:
            notes.extend(plan.warnings)
        for index, note in enumerate(notes, 1):
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
            cell = ws.cell(row, 1, f"{index}. {note}")
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if "不得" in note or "必须" in note:
                cell.fill = _WARNING_FILL
            row += 1
        ws.freeze_panes = "A2"

    def _write_procedure_sheet(self, ws, plan: AuditPlan) -> None:
        headers = ["程序", "程序名称", "依赖", "必需输入", "缺失输入", "工具", "人工", "重试次数", "状态", "说明"]
        self._table_header(ws, headers, [10, 26, 14, 24, 24, 34, 10, 12, 18, 38])
        for row_index, step in enumerate(plan.steps, 2):
            values = [
                step.step_id,
                step.name,
                "、".join(step.dependencies),
                "、".join(step.required_inputs),
                "、".join(step.missing_inputs),
                "、".join(step.required_tools),
                "是" if step.human_required else "否",
                step.retry_count,
                STATUS_LABELS.get(step.status.value, step.status.value),
                step.notes,
            ]
            for col, value in enumerate(values, 1):
                cell = ws.cell(row_index, col, value)
                cell.border = _BORDER
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            self._status_fill(ws.cell(row_index, 9), step.status.value)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    def _write_evidence_sheet(self, ws, evidence: list[Evidence]) -> None:
        headers = ["证据 ID", "程序", "类型", "状态", "工具/来源", "源文件", "源 SHA256", "结果文件", "可追溯", "需人工复核", "结论"]
        self._table_header(ws, headers, [20, 10, 18, 14, 18, 34, 28, 34, 10, 12, 42])
        for row_index, item in enumerate(evidence, 2):
            values = [
                item.evidence_id,
                item.procedure_id,
                item.kind.value,
                item.status.value,
                item.tool_name,
                item.source_file or "",
                item.source_sha256 or "",
                item.result_file or "",
                "是" if item.traceable else "否",
                "是" if item.requires_human_review else "否",
                item.conclusion,
            ]
            for col, value in enumerate(values, 1):
                cell = ws.cell(row_index, col, value)
                cell.border = _BORDER
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            ws.cell(row_index, 9).fill = _SUCCESS_FILL if item.traceable else _WARNING_FILL
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    def _write_revision_sheet(self, ws, task: AuditTask, prepared_by: str, reviewer: str) -> None:
        headers = ["版本", "日期", "编制/修改人", "审核人", "变更说明"]
        self._table_header(ws, headers, [12, 22, 20, 20, 56])
        values = ["v1.0", task.created_at.date().isoformat(), prepared_by, reviewer, "Runtime 自动生成首版执行底稿"]
        for col, value in enumerate(values, 1):
            cell = ws.cell(2, col, value)
            cell.border = _BORDER
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"

    @staticmethod
    def _section(ws, row: int, columns: int, text: str) -> None:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=columns)
        cell = ws.cell(row, 1, text)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _SECTION_FILL
        cell.alignment = Alignment(vertical="center")

    @staticmethod
    def _table_header(ws, headers: list[str], widths: list[int]) -> None:
        for col, (header, width) in enumerate(zip(headers, widths, strict=True), 1):
            cell = ws.cell(1, col, header)
            cell.font = Font(bold=True)
            cell.fill = _HEADER_FILL
            cell.border = _BORDER
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.column_dimensions[get_column_letter(col)].width = width
        ws.row_dimensions[1].height = 26

    @staticmethod
    def _widths(ws, widths: list[int]) -> None:
        for index, width in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(index)].width = width

    @staticmethod
    def _status_fill(cell, status: str) -> None:
        if status == "VERIFIED":
            cell.fill = _SUCCESS_FILL
        elif status in {"FAILED", "BLOCKED"}:
            cell.fill = _DANGER_FILL
        elif status in {"WAITING_HUMAN", "HUMAN_COMPLETED"}:
            cell.fill = _WARNING_FILL

    @staticmethod
    def _render_markdown(
        project: AuditProject,
        task: AuditTask,
        plan: AuditPlan,
        evidence: list[Evidence],
        prepared_by: str,
        reviewer: str,
    ) -> str:
        lines = [
            f"# Z-1-2-00 银行存款审计程序执行底稿",
            "",
            "## 一、项目基本信息",
            "",
            f"- 被审计单位：{project.client_label or project.name}",
            f"- 审计期间：{project.period}",
            f"- 项目 ID：{project.project_id}",
            f"- 任务 ID：{task.task_id}",
            f"- 技能：{plan.skill_id} {plan.skill_version}",
            f"- 编制人：{prepared_by}",
            f"- 审核人：{reviewer or '待复核'}",
            "",
            "## 二、审计目标和程序说明",
            "",
            "执行银行存款审计程序，形成可追溯的执行记录；本底稿不构成审计意见。",
            "",
            "| 程序 | 名称 | 执行方式 | 状态 | 索引 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for step in plan.steps:
            lines.append(
                f"| {step.step_id} | {step.name} | {step.execution_mode.value} | "
                f"{STATUS_LABELS.get(step.status.value, step.status.value)} | {step.workpaper_index or '—'} |"
            )
        lines.extend(
            [
                "",
                "## 三、审计程序执行结果",
                "",
                f"- 已通过程序：{sum(1 for step in plan.steps if step.status.value == 'VERIFIED')}",
                f"- 等待人工程序：{sum(1 for step in plan.steps if step.status.value == 'WAITING_HUMAN')}",
                f"- 证据数量：{len(evidence)}",
                f"- 可追溯证据：{sum(1 for item in evidence if item.traceable)}",
                "",
                "## 四、审计说明",
                "",
                "- 差异类结论必须待项目组人工确认。",
                "- 未通过复核的证据不得用于关闭程序。",
                "- 工具结果、人工材料和文件哈希均保留在本任务工作区。",
            ]
        )
        if plan.warnings:
            lines.append("")
            lines.append("### 计划警告")
            lines.extend(f"- {warning}" for warning in plan.warnings)
        return "\n".join(lines) + "\n"


__all__ = ["WorkpaperWriter"]
