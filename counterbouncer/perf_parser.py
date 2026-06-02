"""Parse perf stat JSON Lines without merging different PMUs or inventing zeros."""
from dataclasses import dataclass
import json
import math


@dataclass(frozen=True)
class Event:
    name: str
    value: float | None
    event_runtime_ns: float | None
    pcnt_running: float | None
    status: str
    raw: dict

    @property
    def event_runtime_ms(self):
        return None if self.event_runtime_ns is None else self.event_runtime_ns / 1_000_000


@dataclass(frozen=True)
class ParseResult:
    events: list[Event]
    metadata: list[dict]
    diagnostics: list[str]


class PerfParseError(ValueError):
    pass


def number(value, field):
    if value is None:
        return None
    if isinstance(value, bool):
        raise PerfParseError(f'{field}: boolean is not a number')
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise PerfParseError(f'{field}: invalid numeric value {value!r}') from exc
    if not math.isfinite(result) or result < 0:
        raise PerfParseError(f'{field}: expected finite nonnegative number')
    return result


def parse_perf(text: str) -> ParseResult:
    events, metadata, diagnostics = [], [], []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith(('WARNING:', 'Error:')):
            diagnostics.append(line)
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PerfParseError(f'line {lineno}: invalid JSON') from exc
        if not isinstance(row, dict):
            raise PerfParseError(f'line {lineno}: expected JSON object')
        if 'event' not in row:
            if 'counter-value' in row:
                raise PerfParseError(f'line {lineno}: counter without event name')
            metadata.append(row)
            continue
        name = row['event']
        if not isinstance(name, str) or not name:
            raise PerfParseError(f'line {lineno}: invalid event name')
        raw_value = row.get('counter-value')
        statuses = {'<not supported>': 'unsupported', '<not counted>': 'not_counted'}
        if isinstance(raw_value, str) and raw_value.strip() in statuses:
            value, status = None, statuses[raw_value.strip()]
        elif raw_value is None:
            value, status = None, 'missing_value'
        else:
            value, status = number(raw_value, 'counter-value'), 'counted'
        runtime = number(row.get('event-runtime'), 'event-runtime')
        ratio = number(row.get('pcnt-running'), 'pcnt-running')
        if ratio is not None and ratio > 100:
            raise PerfParseError(f'line {lineno}: pcnt-running exceeds 100')
        events.append(Event(name, value, runtime, ratio, status, row))
    return ParseResult(events, metadata, diagnostics)
