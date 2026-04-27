import re
from html import escape
from string import Formatter


class TemplateError(Exception):
    pass


_PERCENT = re.compile(r"\{%(\d+)(:[^}]*)?\}")


def _normalise(template: str) -> str:
    return _PERCENT.sub(lambda m: "{p" + m.group(1) + (m.group(2) or "") + "}", template)


class _SafeFormatter(Formatter):
    def __init__(self, fields: dict[str, str]) -> None:
        self._fields = fields

    def get_field(self, field_name: str, args, kwargs):
        if field_name not in self._fields:
            raise TemplateError(f"unknown placeholder '{{{field_name}}}'")
        return self._fields[field_name], field_name

    def format_field(self, value, format_spec: str) -> str:
        if format_spec == "raw":
            return str(value)
        if format_spec:
            raise TemplateError(f"unsupported format spec ':{format_spec}'")
        return escape(str(value), quote=True)


def render(template: str, fields: dict[str, str]) -> str:
    normalised = _normalise(template)
    return _SafeFormatter(fields).format(normalised)
