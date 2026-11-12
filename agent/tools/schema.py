"""Runtime 所需的最小 JSON Schema 校验器。

只支持工具契约实际使用的基础关键字，避免引入第三方依赖。
"""

from __future__ import annotations

from typing import Any


class SchemaValidationError(ValueError):
    """参数或结果不符合 ToolSpec 中的 JSON Schema。"""


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def validate_json_schema(value: Any, schema: dict[str, Any], *, path: str = "$") -> None:
    """校验基础 JSON Schema 子集，失败时抛 :class:`SchemaValidationError`。"""
    if not schema:
        return

    expected = schema.get("type")
    if expected is not None:
        allowed = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, str(item)) for item in allowed):
            raise SchemaValidationError(f"{path} 类型应为 {allowed}，实际为 {type(value).__name__}")

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        raise SchemaValidationError(f"{path} 必须是 {enum!r} 之一")

    if isinstance(value, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                raise SchemaValidationError(f"{path}.{key} 为必需字段")
        properties = schema.get("properties") or {}
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, dict):
                validate_json_schema(value[key], child_schema, path=f"{path}.{key}")
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise SchemaValidationError(f"{path} 存在未允许字段：{extras}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if min_items is not None and len(value) < int(min_items):
            raise SchemaValidationError(f"{path} 至少需要 {min_items} 项")
        if max_items is not None and len(value) > int(max_items):
            raise SchemaValidationError(f"{path} 最多允许 {max_items} 项")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                validate_json_schema(item, item_schema, path=f"{path}[{index}]")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if min_length is not None and len(value) < int(min_length):
            raise SchemaValidationError(f"{path} 长度至少为 {min_length}")
        if max_length is not None and len(value) > int(max_length):
            raise SchemaValidationError(f"{path} 长度最多为 {max_length}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            raise SchemaValidationError(f"{path} 不得小于 {minimum}")
        if maximum is not None and value > maximum:
            raise SchemaValidationError(f"{path} 不得大于 {maximum}")
