"""Python Runtime 与 auditox-tools Node 内核之间的受控桥。"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any


DEFAULT_NODE_TOOLS = (
    "bank_reconcile_dual",
    "recalc_check",
    "threshold_flag",
    "rule_check",
    "balance_confirm",
    "index_numbering",
    "sampling_draw",
    "manifest_json",
    "revision_record",
    "workpaper_fill",
    "recon_statement_recalc",
    "ageing_bucket",
    "provision_calc",
    "depreciation_calc",
    "interest_calc",
    "cutoff_test",
    "workpaper_spec",
    "xlsx_export",
    "wp_to_docx",
    "pdf_to_word",
    "pdf_tables_to_excel",
    "pdf_ops",
    "excel_read",
    "excel_write",
    "sheet_to_csv",
    "csv_to_sheet",
)


class NodeBridgeError(RuntimeError):
    """Node 桥错误基类。"""


class NodeBridgeTransportError(NodeBridgeError):
    """进程启动、超时或协议错误。"""


class NodeToolError(NodeBridgeError):
    """Node 工具明确返回的业务错误。"""


class NodeToolBridge:
    """固定脚本、固定白名单、JSON Lines 协议的 Node 子进程桥。"""

    def __init__(
        self,
        project_root: Path,
        *,
        allowed_tools: tuple[str, ...] = DEFAULT_NODE_TOOLS,
        node_executable: str | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.auditox_root = self.project_root / "skill-tools" / "auditox-tools"
        self.bridge_path = self.auditox_root / "scripts" / "runtime_bridge.mjs"
        if not self.bridge_path.is_file():
            raise FileNotFoundError(f"Node Runtime 桥不存在：{self.bridge_path}")
        executable = node_executable or shutil.which("node")
        if not executable:
            raise FileNotFoundError("未找到 node 可执行文件")
        self.node_executable = executable
        self.allowed_tools = frozenset(allowed_tools)
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._request_id = 0

    async def _ensure_started(self) -> asyncio.subprocess.Process:
        if self._process is not None and self._process.returncode is None:
            return self._process
        env = dict(os.environ)
        env.setdefault("NODE_NO_WARNINGS", "1")
        env["AUDITOX_RUNTIME_BRIDGE"] = "1"
        self._process = await asyncio.create_subprocess_exec(
            self.node_executable,
            str(self.bridge_path),
            cwd=str(self.auditox_root),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        return self._process

    async def _reset_unlocked(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    async def _request(self, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        async with self._lock:
            process = await self._ensure_started()
            self._request_id += 1
            request_id = str(self._request_id)
            request = {"id": request_id, **payload}
            assert process.stdin is not None
            assert process.stdout is not None
            try:
                process.stdin.write(
                    (json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                )
                await process.stdin.drain()
                line = await asyncio.wait_for(process.stdout.readline(), timeout=timeout)
                if not line:
                    raise NodeBridgeTransportError("Node Runtime 桥意外关闭")
                response = json.loads(line.decode("utf-8"))
                if response.get("id") != request_id:
                    raise NodeBridgeTransportError("Node Runtime 桥响应 ID 不匹配")
                if not response.get("ok"):
                    raise NodeToolError(str(response.get("error") or "Node 工具执行失败"))
                return response
            except NodeToolError:
                raise
            except (asyncio.TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                await self._reset_unlocked()
                raise NodeBridgeTransportError(f"Node Runtime 桥调用失败：{exc}") from exc
            except NodeBridgeTransportError:
                await self._reset_unlocked()
                raise

    async def list_tools(self, *, timeout: float = 15.0) -> list[dict[str, Any]]:
        response = await self._request({"op": "list"}, timeout=timeout)
        tools = response.get("tools")
        if not isinstance(tools, list):
            raise NodeBridgeTransportError("Node Runtime 桥未返回工具清单")
        names = {str(item.get("name")) for item in tools if isinstance(item, dict)}
        if names != set(self.allowed_tools):
            raise NodeBridgeTransportError(
                f"Node Runtime 桥工具清单与预期不一致：{sorted(names)}"
            )
        return tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        if name not in self.allowed_tools:
            raise NodeBridgeTransportError(f"工具不在 Python 桥白名单：{name}")
        response = await self._request(
            {"op": "execute", "tool": name, "arguments": arguments},
            timeout=timeout,
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise NodeBridgeTransportError(f"Node 工具 {name} 未返回对象结果")
        return result

    async def close(self) -> None:
        async with self._lock:
            process = self._process
            if process is None:
                return
            if process.returncode is None and process.stdin is not None:
                try:
                    self._request_id += 1
                    request = {"id": str(self._request_id), "op": "close"}
                    process.stdin.write(
                        (json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8")
                    )
                    await process.stdin.drain()
                    await asyncio.wait_for(process.wait(), timeout=2)
                except (asyncio.TimeoutError, OSError):
                    await self._reset_unlocked()
                else:
                    self._process = None
