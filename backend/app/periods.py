"""Periodos de reporte: trimestres (F6, T1.2) y meses (cortes de suscripciones)."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .config import settings

MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
MESES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def tz() -> ZoneInfo:
    return ZoneInfo(settings.TIMEZONE)


def now() -> datetime:
    return datetime.now(tz())


def today() -> date:
    return now().date()


def last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


@dataclass(frozen=True)
class Period:
    kind: str  # "quarter" | "month"
    year: int
    number: int  # trimestre 1-4 o mes 1-12

    @property
    def id(self) -> str:
        return f"{self.year}-T{self.number}" if self.kind == "quarter" else f"{self.year}-{self.number:02d}"

    @property
    def start(self) -> date:
        month = (self.number - 1) * 3 + 1 if self.kind == "quarter" else self.number
        return date(self.year, month, 1)

    @property
    def end(self) -> date:
        month = self.number * 3 if self.kind == "quarter" else self.number
        return last_day(self.year, month)

    @property
    def label(self) -> str:
        if self.kind == "quarter":
            return f"{self.year} · Trimestre {self.number}"
        return f"{MESES[self.number - 1]} {self.year}"

    @property
    def sub_label(self) -> str:
        return f"Trimestre {self.number}" if self.kind == "quarter" else MESES[self.number - 1]

    def months(self) -> list["Period"]:
        """Meses que componen el periodo (3 para trimestre)."""
        if self.kind == "month":
            return [self]
        first = (self.number - 1) * 3 + 1
        return [Period("month", self.year, m) for m in range(first, first + 3)]

    def quarter(self) -> "Period":
        """Trimestre al que pertenece el periodo (un mes → su trimestre; un trimestre → él mismo)."""
        if self.kind == "quarter":
            return self
        return Period("quarter", self.year, (self.number - 1) // 3 + 1)

    @property
    def month_in_quarter(self) -> int:
        """Posición del mes dentro de su trimestre (1-3): es la variable MES del F6."""
        return (self.number - 1) % 3 + 1 if self.kind == "month" else 3

    def is_closed(self, ref: date | None = None) -> bool:
        """Cerrado = ya llegó el último día del periodo (el reporte se genera ese día)."""
        return (ref or today()) >= self.end

    def file_token(self) -> str:
        return f"{self.year}_T{self.number}" if self.kind == "quarter" else f"{self.year}_{self.number:02d}"

    def next(self) -> "Period":
        size = 4 if self.kind == "quarter" else 12
        if self.number == size:
            return Period(self.kind, self.year + 1, 1)
        return Period(self.kind, self.year, self.number + 1)

    def prev(self) -> "Period":
        size = 4 if self.kind == "quarter" else 12
        if self.number == 1:
            return Period(self.kind, self.year - 1, size)
        return Period(self.kind, self.year, self.number - 1)


def parse_period(kind: str, period_id: str) -> Period:
    try:
        year_s, rest = period_id.split("-", 1)
        year = int(year_s)
        if kind == "quarter":
            if not rest.upper().startswith("T"):
                raise ValueError
            number = int(rest[1:])
            if not 1 <= number <= 4:
                raise ValueError
        else:
            number = int(rest)
            if not 1 <= number <= 12:
                raise ValueError
    except ValueError as exc:  # noqa: B904
        raise ValueError(f"Periodo inválido: {period_id}") from exc
    return Period(kind, year, number)


def current_period(kind: str, ref: date | None = None) -> Period:
    d = ref or today()
    if kind == "quarter":
        return Period("quarter", d.year, (d.month - 1) // 3 + 1)
    return Period("month", d.year, d.month)


def first_period(kind: str) -> Period:
    year_s, month_s = (settings.HISTORY_START or "2025-01").split("-")
    year, month = int(year_s), int(month_s)
    if kind == "quarter":
        return Period("quarter", year, (month - 1) // 3 + 1)
    return Period("month", year, month)


def all_periods(kind: str, ref: date | None = None) -> list[Period]:
    """Del periodo actual (abierto) hacia atrás hasta HISTORY_START, más reciente primero."""
    current = current_period(kind, ref)
    first = first_period(kind)
    out: list[Period] = []
    p = current
    while (p.year, p.number) >= (first.year, first.number):
        out.append(p)
        p = p.prev()
    return out


def fmt_date(d: date | datetime | None) -> str:
    if d is None:
        return "—"
    return f"{d.day} {MESES_CORTO[d.month - 1]} {d.year}"


def fmt_datetime(d: datetime | None) -> str:
    if d is None:
        return "—"
    return f"{fmt_date(d)} · {d:%H:%M}"
