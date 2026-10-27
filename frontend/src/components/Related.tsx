import { motion } from "framer-motion";
import type { PeriodRow, RelatedCheck, RelatedLink } from "../api/types";
import btnDownload from "../assets/figma/btn-download.svg";
import btnLoader from "../assets/figma/btn-loader.svg";
import estadoAlert from "../assets/figma/estado-alert.svg";
import estadoCheck from "../assets/figma/estado-check.svg";
import { periodKey, useActions, versionKey } from "../lib/actions";

const NUM = new Intl.NumberFormat("es-CO");

function CheckPill({ check }: { check: RelatedCheck }) {
  const title = check.ok
    ? `${check.label}: ${NUM.format(check.cut_value)} en el corte y en el reporte trimestral (cuadra).`
    : `${check.label}: ${NUM.format(check.cut_value)} en el corte, ${NUM.format(check.report_value)} en el reporte trimestral. Regenera el que esté desactualizado.`;
  return (
    <span className={`rcheck ${check.ok ? "rcheck--ok" : "rcheck--warn"}`} title={title}>
      <img src={check.ok ? estadoCheck : estadoAlert} alt="" width={12} height={12} />
      {NUM.format(check.cut_value)}
      {!check.ok && <span className="rcheck__diff">≠ {NUM.format(check.report_value)}</span>}
    </span>
  );
}

/** Chip de un periodo relacionado: descarga su Excel o lo genera si el periodo ya cerró. */
function RelatedChip({ link, name }: { link: RelatedLink; name: string }) {
  const actions = useActions();
  const v = link.available;
  const busy =
    link.status === "processing" ||
    actions.isBusy(periodKey(link.report, link.period)) ||
    (v ? actions.isBusy(versionKey(v.id)) : false);
  const canGenerate = !v && link.closed && actions.canGenerate;
  const disabled = busy || (!v && !canGenerate);
  const state = busy ? "proc" : v ? "ok" : link.status === "error" ? "error" : link.closed ? "none" : "pending";
  const meta = busy
    ? "Preparando…"
    : v
      ? `v${v.version}`
      : link.status === "error"
        ? actions.canGenerate
          ? "Reintentar"
          : "Error"
        : link.closed
          ? actions.canGenerate
            ? "Generar"
            : "Sin generar"
          : "Pendiente";
  const title = v
    ? `Descargar ${v.filename}`
    : canGenerate
      ? `Generar y descargar ${link.short} · ${link.label}`
      : link.closed
        ? `${link.short} · ${link.label} sin generar. ${actions.deniedReason}`
        : `${link.short} · ${link.label}: se genera automáticamente al cierre del periodo`;
  const onClick = () => {
    if (v) actions.download(v);
    else if (canGenerate) actions.generate(link.report, link.period, { downloadWhenReady: true });
  };
  return (
    <span className="rlink">
      <motion.button
        type="button"
        className={`rchip rchip--${state}`}
        onClick={disabled ? undefined : onClick}
        disabled={disabled}
        aria-busy={busy}
        title={title}
        whileTap={disabled ? undefined : { scale: 0.96 }}
      >
        <span className="rchip__dot" aria-hidden />
        <span className="rchip__name">{name}</span>
        <span className="rchip__meta">{meta}</span>
        {busy ? (
          <img src={btnLoader} alt="" width={13} height={13} className="spin" />
        ) : (
          v && <img src={btnDownload} alt="" width={13} height={13} className="rchip__ic" />
        )}
      </motion.button>
      {link.check && <CheckPill check={link.check} />}
    </span>
  );
}

/**
 * Relación corte mensual ↔ reporte trimestral, debajo de cada fila:
 * - En F6 / T1.2: los 3 cortes mensuales del trimestre.
 * - En Cortes: el F6 y el T1.2 del trimestre al que pertenece el mes.
 */
export function RelatedRow({ row, card }: { row: PeriodRow; card?: boolean }) {
  const rel = row.related;
  if (!rel || rel.items.length === 0) return null;
  const q = rel.quarter;
  const label = q ? `Trimestre ${q.number} · ${q.year} — mes ${q.mes_trim} de 3` : "Cortes mensuales";
  return (
    <div className={card ? "rel-card" : "rel-row"}>
      <span className="rel__label">{label}</span>
      <div className="rel__items">
        {rel.items.map((link) => (
          <RelatedChip key={`${link.report}:${link.period}`} link={link} name={q ? link.short : link.sub_label} />
        ))}
      </div>
    </div>
  );
}
