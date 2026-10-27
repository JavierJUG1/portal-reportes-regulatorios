export type VersionStatus = "available" | "processing" | "error";
export type RowStatus = VersionStatus | "not_generated" | "pending";
export type ReportKey = "f6" | "t12" | "cortes";

export interface User {
  email: string;
  name: string;
  role_label: string;
  initials: string;
  roles: string[];
  source: "debug" | "erpnext";
  /** Rol de generación verificado en ERPNext (GENERATE_ROLES, por defecto System Manager). */
  can_generate?: boolean;
  generate_denied_reason?: string | null;
  generate_roles?: string[];
}

export interface AuthConfig {
  mode: "debug" | "erpnext";
  oauth_ready: boolean;
  env_label: string;
  erpnext_url: string;
}

export interface Version {
  id: number;
  report: ReportKey;
  report_name: string;
  report_short: string;
  report_icon: "file" | "users";
  period: string;
  period_label: string;
  version: number;
  status: VersionStatus;
  filename: string | null;
  created_at: string;
  generated_at: string | null;
  generated_at_label: string;
  generated_date_label: string;
  generated_by: string;
  generated_by_name: string;
  /** Generación automática del calendario: se muestra "Generado por el sistema". */
  generated_by_system?: boolean;
  trigger: string;
  error: string | null;
  size_bytes: number | null;
  warnings: string[];
  tag?: "vigente" | "reemplazada" | null;
  /** Solo cortes mensuales: trimestre al que pertenecen. */
  quarter?: QuarterRef | null;
  year?: number;
  kind?: "quarter" | "month";
  number?: number;
}

export interface QuarterRef {
  period: string;
  label: string;
  year: number;
  number: number;
  /** Posición del mes en el trimestre (1-3) = variable MES del F6. */
  mes_trim: number;
}

/** Cuadre entre el total del reporte trimestral y el del corte mensual. */
export interface RelatedCheck {
  label: string;
  report_value: number;
  cut_value: number;
  ok: boolean;
}

/** Periodo de otro reporte ligado a esta fila (cortes del trimestre, o F6/T1.2 del corte). */
export interface RelatedLink {
  report: ReportKey;
  short: string;
  period: string;
  label: string;
  sub_label: string;
  closed: boolean;
  status: RowStatus;
  latest: Version | null;
  available: Version | null;
  mes_trim?: number;
  check: RelatedCheck | null;
}

export interface Related {
  quarter: QuarterRef | null;
  items: RelatedLink[];
}

export interface PeriodRow {
  period: string;
  label: string;
  year: number;
  number: number;
  start: string;
  end: string;
  closed: boolean;
  closing_label: string;
  status: RowStatus;
  latest: Version | null;
  available: Version | null;
  versions_count: number;
  related?: Related | null;
}

export interface ReportSummary {
  key: ReportKey;
  name: string;
  short: string;
  icon: "file" | "users";
  frequency: string;
  kind: "quarter" | "month";
  unit: { singular: string; plural: string };
  current: PeriodRow;
  latest_available: Version | null;
}

export interface Dashboard {
  reports: ReportSummary[];
  recent: Version[];
}

export interface Meta {
  env_label: string;
  data_source: string;
  last_sync: string | null;
  last_sync_label: string | null;
  schedule: Record<string, string | null>;
  reports: { key: ReportKey; name: string; short: string; kind: "quarter" | "month" }[];
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  years: number[];
}

export interface PeriodsPage extends Paged<PeriodRow> {
  unit: { singular: string; plural: string };
  sub_options: { value: number; label: string }[];
}
