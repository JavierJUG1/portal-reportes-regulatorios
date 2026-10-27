import { AnimatePresence, motion } from "framer-motion";
import type { PeriodRow, ReportKey } from "../api/types";
import btnRefresh from "../assets/figma/btn-refresh.svg";
import errInfo from "../assets/figma/errrow-info.svg";
import rowSheet from "../assets/figma/row-sheet.svg";
import thSort from "../assets/figma/th-sort.svg";
import { periodKey, useActions } from "../lib/actions";
import { generatedBy, rowErrorMessage } from "../lib/format";
import { RelatedRow } from "./Related";
import { PeriodAction } from "./RowAction";
import { Estado } from "./ui";

const EASE = [0.22, 1, 0.36, 1] as const;

export function SortHeader({ label, field, sort, onSort, className }: {
  label: string;
  field: "period" | "generated";
  sort: string;
  onSort: (s: string) => void;
  className: string;
}) {
  const active = sort.startsWith(field);
  const dir = active && sort.endsWith("asc") ? "asc" : "desc";
  return (
    <div className={`cell ${className}`}>
      <button
        type="button"
        className={`th-sort ${active ? "is-active" : ""}`}
        onClick={() => onSort(`${field}_${active && dir === "desc" ? "asc" : "desc"}`)}
        aria-label={`Ordenar por ${label.toLowerCase()}`}
      >
        <span className="th">{label}</span>
        <img src={thSort} alt="" width={12} height={12} className={active ? `sort-${dir}` : undefined} />
      </button>
    </div>
  );
}

function Generated({ row }: { row: PeriodRow }) {
  if (row.status === "processing") return <span className="cell-strong-14">En curso</span>;
  if (!row.latest) return <span className="cell-strong-14">{row.closing_label}</span>;
  return (
    <span className="stack">
      <span className="cell-strong-14">{row.latest.generated_at_label}</span>
      <span className="sub-12">{generatedBy(row.latest)}</span>
    </span>
  );
}

function VersionCell({ report, row }: { report: ReportKey; row: PeriodRow }) {
  const actions = useActions();
  const showVersion = row.latest && row.status !== "processing";
  return (
    <span className="ver">
      {showVersion ? <span className="ver__n">v{row.latest!.version}</span> : <span className="ver__none">—</span>}
      {row.status === "available" && actions.canGenerate && !actions.isBusy(periodKey(report, row.period)) && (
        <button
          type="button"
          className="regen"
          title={`Generar nueva versión (v${(row.latest?.version ?? 0) + 1}) con datos actuales de ERPNext`}
          aria-label="Generar nueva versión"
          onClick={() => actions.generate(report, row.period)}
        >
          <img src={btnRefresh} alt="" width={14} height={14} />
        </button>
      )}
    </span>
  );
}

export function PeriodTable({ report, kind, rows, sort, onSort, animKey }: {
  report: ReportKey;
  kind: "quarter" | "month";
  rows: PeriodRow[];
  sort: string;
  onSort: (s: string) => void;
  animKey: string;
}) {
  return (
    <div className="table" role="table" aria-label="Periodos">
      <div className="thead trow cols-periods" role="row">
        <SortHeader label="PERIODO" field="period" sort={sort} onSort={onSort} className="cell--main" />
        <SortHeader label="GENERADO" field="generated" sort={sort} onSort={onSort} className="cell--gen" />
        <div className="cell cell--ver"><span className="th">VERSIÓN</span></div>
        <div className="cell cell--estado"><span className="th">ESTADO</span></div>
        <div className="cell cell--accion"><span className="th">ACCIÓN</span></div>
      </div>
      <div key={animKey}>
        {rows.map((row, i) => (
          <motion.div
            key={row.period}
            className={`trow-wrap ${row.related?.items.length ? "trow-wrap--rel" : ""}`}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, delay: Math.min(i * 0.025, 0.2), ease: EASE }}
          >
            <div className={`trow cols-periods ${row.status === "error" ? "trow--error" : ""}`} role="row">
              <div className="cell cell--main">
                <span className="row-ic"><img src={rowSheet} alt="" width={16} height={16} /></span>
                <span className="stack">
                  <span className="cell-title">{row.label}</span>
                  <span className="sub-12">{row.status === "available" ? row.latest?.filename : "—"}</span>
                </span>
              </div>
              <div className="cell cell--gen"><Generated row={row} /></div>
              <div className="cell cell--ver"><VersionCell report={report} row={row} /></div>
              <div className="cell cell--estado"><Estado status={row.status} /></div>
              <div className="cell cell--accion"><PeriodAction report={report} row={row} /></div>
            </div>
            <AnimatePresence initial={false}>
              {row.status === "error" && (
                <motion.div
                  className="err-row"
                  role="alert"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.18, ease: EASE }}
                >
                  <img src={errInfo} alt="" width={14} height={14} />
                  <span>{rowErrorMessage(kind, row)}</span>
                </motion.div>
              )}
            </AnimatePresence>
            <RelatedRow row={row} />
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- móvil */
export function PeriodCards({ report, rows, animKey }: { report: ReportKey; rows: PeriodRow[]; animKey: string }) {
  return (
    <div className="pcards" key={animKey}>
      {rows.map((row, i) => (
        <motion.article
          key={row.period}
          className="pcard"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, delay: Math.min(i * 0.03, 0.2), ease: EASE }}
        >
          <div className="pcard__head">
            <span className="stack stack--3">
              <span className="pcard__title">{row.label}</span>
              <span className="sub-12">{row.status === "available" ? row.latest?.filename : "—"}</span>
            </span>
            <Estado status={row.status} />
          </div>
          <div className="pcard__meta">
            <span className="kv">
              <span className="kv__k">GENERADO</span>
              <span className="kv__v">
                {row.status === "processing" ? "En curso" : row.latest ? row.latest.generated_date_label : row.closing_label}
              </span>
            </span>
            <span className="kv">
              <span className="kv__k">VERSIÓN</span>
              <span className="kv__v">{row.latest && row.status !== "processing" ? `v${row.latest.version}` : "—"}</span>
            </span>
          </div>
          <RelatedRow row={row} card />
          <PeriodAction report={report} row={row} full />
        </motion.article>
      ))}
    </div>
  );
}
