import type { PeriodRow, ReportKey, Version } from "../api/types";

export const SYSTEM_LABEL = "Generado por el sistema";

/** "Generado por el sistema" para las automáticas; "por Nombre" (o solo el nombre) para las de un usuario. */
export function generatedBy(v: Pick<Version, "generated_by_system" | "generated_by_name">, bare = false): string {
  if (v.generated_by_system) return SYSTEM_LABEL;
  return bare ? v.generated_by_name : `por ${v.generated_by_name}`;
}

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
  "noviembre", "diciembre"];

export function periodPhrase(kind: "quarter" | "month", row: Pick<PeriodRow, "year" | "number">): string {
  return kind === "month" ? `de ${MESES[row.number - 1]}` : `del trimestre ${row.number} de ${row.year}`;
}

export function rowErrorMessage(kind: "quarter" | "month", row: PeriodRow): string {
  const others = kind === "month" ? "meses" : "periodos";
  const reason = row.latest?.error ? ` Motivo: ${row.latest.error}` : "";
  const older = row.available ? ` La versión v${row.available.version} sigue disponible en Historial.` : "";
  return `No pudimos generar el archivo ${periodPhrase(kind, row)}. Puedes reintentar; los demás ${others} no se ven afectados.${reason}${older}`;
}

export function showingText(page: number, pageSize: number, total: number, plural: string, compact = false): string {
  if (total === 0) return compact ? `0 de 0` : `Sin ${plural}`;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return compact ? `${from}–${to} de ${total}` : `Mostrando ${from}–${to} de ${total} ${plural}`;
}

export const REPORT_ROUTES: Record<ReportKey, string> = {
  f6: "/reportes/f6",
  t12: "/reportes/t12",
  cortes: "/reportes/cortes",
};

export function countLabel(n: number, singular: string, plural: string): string {
  return `${n} ${n === 1 ? singular : plural}`;
}
