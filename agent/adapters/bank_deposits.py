"""Deterministic adapter for z-1-2 bank deposits.

It reads the logical task inputs, normalizes the rows needed by the central
tools, and produces the tool calls for P01/P04/P06/P08/P10. It never infers
audit conclusions; it only prepares deterministic inputs for the tools.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from agent.adapters.base import AdapterError, SkillAdapter
from agent.adapters.table import TableReadError, TableRow, read_table
from agent.models.execution import ToolCall
from agent.models.plan import PlanStep
from agent.models.task import AuditTask


@dataclass(frozen=True)
class BankAccount:
    account_id: str
    bank_name: str
    account_type: str
    currency: str
    original_amount: Decimal
    book_rate: Decimal
    book_rmb: Decimal
    statement_rmb: Decimal
    restricted: str
    official_rate: Decimal

    @property
    def official_rmb(self) -> Decimal:
        if self.currency.upper() == "RMB":
            return self.book_rmb
        return self.original_amount * self.official_rate


class BankDepositsAdapter(SkillAdapter):
    skill_id = "z-1-2-bank-deposits"

    REQUIRED = (
        "bank_balance_detail",
        "bank_journal",
        "bank_statement",
        "bank_reconciliation",
        "interest_income",
        "disclosure_draft",
    )

    def __init__(self, inputs: Mapping[str, Path]) -> None:
        self.inputs = {key: Path(value) for key, value in inputs.items()}
        missing = [key for key in self.REQUIRED if key not in self.inputs]
        if missing:
            raise AdapterError("自动适配缺少输入：" + "、".join(missing))
        try:
            self.calls = self._build_calls()
        except (TableReadError, ValueError, KeyError) as exc:
            raise AdapterError(f"银行存款输入解析失败：{exc}") from exc

    def calls_for(self, _task: AuditTask, step: PlanStep) -> list[ToolCall]:
        return list(self.calls.get(step.step_id, ()))

    def _build_calls(self) -> dict[str, list[ToolCall]]:
        accounts, gl_total, fs_total = self._accounts_and_totals()
        journal = self._transactions(self.inputs["bank_journal"], "journal")
        statement = self._transactions(self.inputs["bank_statement"], "statement")
        recon_items = self._reconciliation_items()
        interest = self._interest()
        disclosure = self._disclosure_flags()

        source_balance = str(self.inputs["bank_balance_detail"])
        source_journal = str(self.inputs["bank_journal"])
        source_statement = str(self.inputs["bank_statement"])
        source_recon = str(self.inputs["bank_reconciliation"])
        source_interest = str(self.inputs["interest_income"])
        source_disclosure = str(self.inputs["disclosure_draft"])
        source_financial = str(self.inputs.get("financial_statement", self.inputs["bank_balance_detail"]))

        book_total = sum((account.book_rmb for account in accounts), Decimal("0"))
        official_total = sum((account.official_rmb for account in accounts), Decimal("0"))

        p04_calls: list[ToolCall] = []
        for account in accounts:
            items = [
                item
                for item in recon_items
                if item["account_id"] == account.account_id
            ]
            p04_calls.append(
                ToolCall(
                    tool_name="recon_statement_recalc",
                    arguments={
                        "book_balance": _number(account.book_rmb),
                        "statement_balance": _number(account.statement_rmb),
                        "items": [
                            {
                                "type": item["type"],
                                "date": item["date"],
                                "amount": _number(item["amount"]),
                                "note": item["note"],
                            }
                            for item in items
                        ],
                        "balance_date": self._balance_date(),
                    },
                    source_files=[source_balance, source_statement, source_recon],
                )
            )
        recon_rows = [
            {
                "id": f"RECON-{index + 1}",
                "amount": _number(item["amount"]),
                "type": item["type"],
                "date": item["date"],
                "note": item["note"],
            }
            for index, item in enumerate(recon_items)
        ]
        p04_calls.append(
            ToolCall(
                tool_name="threshold_flag",
                arguments={
                    "rows": recon_rows,
                    "field": "amount",
                    "thresholds": [
                        {
                            "op": "gte",
                            "value": _number(interest["threshold"]),
                            "label": "大额或长期未达账项",
                        }
                    ],
                },
                source_files=[source_balance, source_statement, source_recon],
            )
        )

        expected_interest = sum(
            (row["average_balance"] * row["annual_rate"] for row in interest["rows"]),
            Decimal("0"),
        )
        interest_diff = expected_interest - interest["book_interest"]
        p08_calls = [
            ToolCall(
                tool_name="recalc_check",
                arguments={
                    "op": "diff",
                    "operands": [_number(expected_interest), _number(interest["book_interest"])],
                    "tolerance": 0,
                },
                source_files=[source_balance, source_interest],
            ),
            ToolCall(
                tool_name="threshold_flag",
                arguments={
                    "rows": [
                        {
                            "id": "INTEREST-DIFF",
                            "amount": _number(abs(interest_diff)),
                        }
                    ],
                    "field": "amount",
                    "thresholds": [
                        {
                            "op": "gte",
                            "value": _number(interest["threshold"]),
                            "label": "利息差异超过重要性阈值",
                        }
                    ],
                },
                source_files=[source_balance, source_interest],
            ),
        ]

        return {
            "P01": [
                ToolCall(
                    tool_name="recalc_check",
                    arguments={
                        "op": "diff",
                        "operands": [_number(gl_total), _number(book_total)],
                        "tolerance": 0,
                    },
                    source_files=[source_balance, str(self.inputs.get("general_ledger", source_balance))],
                ),
                ToolCall(
                    tool_name="balance_confirm",
                    arguments={
                        "book": _number(gl_total),
                        "bank": _number(official_total),
                        "tolerance_abs": 0,
                    },
                    source_files=[source_balance, source_financial],
                ),
            ],
            "P04": p04_calls,
            "P06": [
                ToolCall(
                    tool_name="bank_reconcile_dual",
                    arguments={
                        "statement": statement,
                        "journal": journal,
                        "tolerance_pct": 0,
                        "match_key": "id",
                        "amount_key": "amount",
                    },
                    source_files=[source_journal, source_statement],
                ),
                ToolCall(
                    tool_name="sampling_draw",
                    arguments={
                        "item_ids": [row["id"] for row in journal],
                        "population_size": len(journal),
                        "sample_size": min(5, max(1, math.ceil(math.sqrt(len(journal))))),
                        "seed": 20261124,
                    },
                    source_files=[source_journal],
                ),
            ],
            "P08": p08_calls,
            "P10": [
                ToolCall(
                    tool_name="rule_check",
                    arguments={
                        "data": disclosure,
                        "schema": {
                            "required": [
                                "bank_deposit_disclosed",
                                "restricted_funds_disclosed",
                                "financial_statement_present",
                                "disclosure_draft_present",
                            ],
                            "properties": {
                                "bank_deposit_disclosed": {"type": "boolean"},
                                "restricted_funds_disclosed": {"type": "boolean"},
                                "financial_statement_present": {"type": "boolean"},
                                "disclosure_draft_present": {"type": "boolean"},
                            },
                        },
                    },
                    source_files=[source_financial, source_disclosure],
                )
            ],
        }

    def _accounts_and_totals(self) -> tuple[list[BankAccount], Decimal, Decimal]:
        rows = read_table(self.inputs["bank_balance_detail"])
        accounts: list[BankAccount] = []
        for row in rows:
            account_id = row.text("账户ID", "账户编号", "账号", "account_id")
            if not account_id:
                continue
            original = row.number("原币金额", "原币余额", "期末原币余额", default=Decimal("0"))
            book_rate = row.number("账面汇率", "汇率", default=Decimal("1"))
            book_rmb = row.number("账面RMB", "账面人民币", "本位币金额")
            if book_rmb is None:
                book_rmb = original * book_rate
            statement_rmb = row.number("对账单RMB", "对账单余额", "银行对账单余额", default=book_rmb)
            official_rate = row.number("官方即期汇率", "期末汇率", "即期汇率", default=book_rate)
            accounts.append(
                BankAccount(
                    account_id=account_id,
                    bank_name=row.text("开户银行", "银行名称"),
                    account_type=row.text("账户性质", "账户类型"),
                    currency=row.text("币种", "货币", default="RMB").upper(),
                    original_amount=original,
                    book_rate=book_rate,
                    book_rmb=book_rmb,
                    statement_rmb=statement_rmb,
                    restricted=row.text("是否受限", "受限情况"),
                    official_rate=official_rate,
                )
            )
        if not accounts:
            raise AdapterError("银行存款明细表中未找到账户行")

        gl_total = self._summary_number(
            self.inputs.get("general_ledger"),
            rows,
            aliases=("总账1002", "总账余额", "账面余额"),
            fallback=sum((account.book_rmb for account in accounts), Decimal("0")),
        )
        fs_total = self._summary_number(
            self.inputs.get("financial_statement"),
            rows,
            aliases=("报表数", "报表余额", "期末余额"),
            fallback=gl_total,
        )
        return accounts, gl_total, fs_total

    def _summary_number(
        self,
        path: Path | None,
        fallback_rows: list[TableRow],
        *,
        aliases: tuple[str, ...],
        fallback: Decimal,
    ) -> Decimal:
        candidates: list[TableRow] = list(fallback_rows)
        if path and path.is_file() and path.resolve() != self.inputs["bank_balance_detail"].resolve():
            candidates.extend(read_table(path))
        for row in candidates:
            value = row.number(*aliases)
            if value is not None:
                return value
        return fallback

    def _transactions(self, path: Path, side: str) -> list[dict[str, Any]]:
        rows = read_table(path)
        result: list[dict[str, Any]] = []
        for row in rows:
            debit = row.number("借方金额", "借方发生额", default=Decimal("0"))
            credit = row.number("贷方金额", "贷方发生额", default=Decimal("0"))
            amount = debit if debit else credit
            if amount == 0:
                continue
            direction = "dr" if debit else "cr"
            date_value = row.date("记账日期", "对账单日期", "日期")
            date_text = date_value.isoformat() if date_value else ""
            counterparty = row.text("收付款单位", "对手名称", "对方单位")
            description = row.text("摘要", "交易摘要")
            match_id = f"{date_text}|{direction}|{_number(amount)}|{counterparty}"
            result.append(
                {
                    "id": match_id,
                    "date": date_text,
                    "description": description,
                    "debit": _number(debit),
                    "credit": _number(credit),
                    "amount": _number(amount),
                    "direction": direction,
                    "counterparty": counterparty,
                    "source": side,
                }
            )
        if not result:
            raise AdapterError(f"{side} 没有可核对的发生额")
        return result

    def _reconciliation_items(self) -> list[dict[str, Any]]:
        rows = read_table(self.inputs["bank_reconciliation"])
        accounts = self._accounts_and_totals()[0]
        target_account = next(
            (account.account_id for account in accounts if account.book_rmb != account.statement_rmb),
            accounts[0].account_id,
        )
        account_ids = {account.account_id for account in accounts}
        items: list[dict[str, Any]] = []
        for row in rows:
            amount = row.number("金额", "未达金额")
            if amount is None:
                continue
            item_date = row.date("日期", "发生日期")
            item_account = row.text("账户ID", "账户", "账号", default=target_account)
            if item_account not in account_ids:
                raise AdapterError(f"未达账项引用了不存在的账户：{item_account}")
            items.append(
                {
                    "account_id": item_account,
                    "type": row.text("类型", "未达类型"),
                    "date": item_date.isoformat() if item_date else "",
                    "amount": amount,
                    "note": row.text("备注", "说明"),
                }
            )
        return items

    def _interest(self) -> dict[str, Any]:
        input_path = self.inputs["interest_income"]
        rate_path = self.inputs.get("interest_rate", input_path)
        income_rows = read_table(input_path)
        rate_rows = read_table(rate_path) if rate_path.resolve() != input_path.resolve() else income_rows

        rate_map: dict[str, Decimal] = {}
        for row in rate_rows:
            account = row.text("账户", "账户ID", "账号")
            rate = row.number("年利率", "利率", "执行利率")
            if account and rate is not None:
                rate_map[account] = rate

        rows: list[dict[str, Any]] = []
        book_interest = Decimal("0")
        materiality = Decimal("0")
        threshold_pct = Decimal("0")
        for row in income_rows:
            account = row.text("账户", "账户ID", "账号")
            avg = row.number("平均余额", "月均余额", "日均余额")
            annual_rate = row.number("年利率", "利率")
            if annual_rate is None and account in rate_map:
                annual_rate = rate_map[account]
            if account and avg is not None and annual_rate is not None:
                rows.append({"account": account, "average_balance": avg, "annual_rate": annual_rate})
            row_interest = row.number("账面利息收入", "利息收入")
            if row_interest is not None:
                book_interest = row_interest
            row_materiality = row.number("实际执行重要性水平", "重要性水平")
            if row_materiality is not None:
                materiality = row_materiality
            row_pct = row.number("阈值百分比", "差异阈值百分比")
            if row_pct is not None:
                threshold_pct = row_pct
        if not rows:
            raise AdapterError("利息收入输入中没有可测算的账户平均余额和利率")
        if book_interest == 0:
            raise AdapterError("利息收入输入缺少账面利息收入")
        if materiality <= 0 or threshold_pct <= 0:
            raise AdapterError("利息分析缺少实际执行重要性水平或阈值百分比")
        threshold = materiality * threshold_pct
        return {
            "rows": rows,
            "book_interest": book_interest,
            "materiality": materiality,
            "threshold_pct": threshold_pct,
            "threshold": threshold,
        }

    def _disclosure_flags(self) -> dict[str, bool]:
        path = self.inputs["disclosure_draft"]
        rows: list[TableRow] = []
        if path.suffix.lower() in {".csv", ".tsv", ".xlsx", ".xlsm"}:
            rows = read_table(path)
            bank_rows = [
                row
                for row in rows
                if "银行存款" in row.text("项目", "披露项目", "科目", default="")
            ]
            restricted_rows = [
                row
                for row in rows
                if "受限" in row.text("项目", "披露项目", "科目", default="")
            ]
            def disclosed(row: TableRow) -> bool:
                return row.text("是否披露", "披露", "状态").strip() in {
                    "是",
                    "true",
                    "True",
                    "已披露",
                    "√",
                }

            bank_disclosed = bool(bank_rows) and any(disclosed(row) for row in bank_rows)
            restricted_disclosed = bool(restricted_rows) and any(disclosed(row) for row in restricted_rows)
        else:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            bank_disclosed = "银行存款" in text
            restricted_disclosed = "受限" in text
        return {
            "bank_deposit_disclosed": bank_disclosed,
            "restricted_funds_disclosed": restricted_disclosed,
            "financial_statement_present": True,
            "disclosure_draft_present": True,
        }

    def _balance_date(self) -> str:
        for key in ("bank_balance_detail", "financial_statement"):
            path = self.inputs.get(key)
            if not path:
                continue
            for row in read_table(path):
                value = row.date("资产负债表日", "报表日", "截止日期")
                if value:
                    return value.isoformat()
        return ""


def _number(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


__all__ = ["BankAccount", "BankDepositsAdapter"]
