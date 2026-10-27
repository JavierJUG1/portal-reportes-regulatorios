import { useMeta } from "../api/hooks";
import type { ReportKey } from "../api/types";

const DEFAULT_ENABLED: ReportKey[] = ["f6", "t12"];

/** Reportes habilitados en el backend (ENABLED_REPORTS). */
export function useEnabledReports(): ReportKey[] {
  const { data } = useMeta();
  return data?.reports.map((r) => r.key) ?? DEFAULT_ENABLED;
}

const PHRASE: Record<ReportKey, string> = {
  f6: "F6",
  t12: "T1.2",
  cortes: "los cortes de suscripciones mensuales",
};

/** "los reportes F6 y T1.2" / "los reportes F6, T1.2 y los cortes de suscripciones mensuales". */
export function reportsPhrase(keys: ReportKey[]): string {
  const parts = keys.map((k) => PHRASE[k]);
  if (parts.length === 0) return "los reportes";
  if (parts.length === 1) return `el reporte ${parts[0]}`;
  return `los reportes ${parts.slice(0, -1).join(", ")} y ${parts[parts.length - 1]}`;
}
