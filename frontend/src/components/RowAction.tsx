import type { PeriodRow, ReportKey, Version } from "../api/types";
import { periodKey, useActions, versionKey } from "../lib/actions";
import { DownloadButton, RetryButton } from "./ui";

/** En lugar de "Generar" / "Reintentar" cuando el usuario no tiene el rol de generación en ERPNext. */
export function NoGenerate({ full }: { full?: boolean }) {
  const { deniedReason } = useActions();
  return (
    <span className={`nogen ${full ? "nogen--full" : ""}`} title={deniedReason}>
      Requiere System Manager
    </span>
  );
}

/** Acción de una fila de periodo según su estado (Figma: columna ACCIÓN). */
export function PeriodAction({ report, row, full, label }: { report: ReportKey; row: PeriodRow; full?: boolean; label?: string }) {
  const actions = useActions();
  const genBusy = actions.isBusy(periodKey(report, row.period));
  const latest = row.latest;
  switch (row.status) {
    case "processing":
      return <DownloadButton busy full={full} />;
    case "available":
      return (
        <DownloadButton
          full={full}
          label={label}
          busy={genBusy || (latest ? actions.isBusy(versionKey(latest.id)) : false)}
          onClick={() => latest && actions.download(latest)}
        />
      );
    case "error":
      if (!actions.canGenerate) return <NoGenerate full={full} />;
      return <RetryButton full={full} busy={genBusy} onClick={() => actions.generate(report, row.period)} />;
    case "not_generated":
      if (!actions.canGenerate) return <NoGenerate full={full} />;
      return (
        <DownloadButton
          full={full}
          label={label}
          busy={genBusy}
          onClick={() => actions.generate(report, row.period, { downloadWhenReady: true })}
        />
      );
    default:
      return <span className="muted-13">No disponible</span>;
  }
}

/** Acción para una versión concreta (Historial y Actividad reciente). */
export function VersionAction({ v, full }: { v: Version; full?: boolean }) {
  const actions = useActions();
  const genBusy = actions.isBusy(periodKey(v.report, v.period));
  if (v.status === "processing") return <DownloadButton busy full={full} />;
  if (v.status === "error") {
    if (!actions.canGenerate) return <NoGenerate full={full} />;
    return <RetryButton full={full} busy={genBusy} onClick={() => actions.generate(v.report, v.period)} />;
  }
  return <DownloadButton full={full} busy={actions.isBusy(versionKey(v.id))} onClick={() => actions.download(v)} />;
}
