import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { usePeriods, useReport } from "../api/hooks";
import type { ReportKey, ReportSummary } from "../api/types";
import btnX from "../assets/figma/btn-x.svg";
import emptyAlert from "../assets/figma/empty-alert.svg";
import emptyHistory from "../assets/figma/empty-history.svg";
import emptyInbox from "../assets/figma/empty-inbox.svg";
import emptySearch from "../assets/figma/empty-search.svg";
import sliders from "../assets/figma/icon-sliders.svg";
import { FilterSheet } from "../components/FilterSheet";
import { PeriodCards, PeriodTable } from "../components/PeriodTable";
import { PeriodAction } from "../components/RowAction";
import { Breadcrumb, PageTitle } from "../components/Shell";
import {
  ActiveFilters, EmptyState, Estado, Pagination, RetryButton, SecondaryButton, Selector, SkeletonRows, type Option,
} from "../components/ui";
import { countLabel, showingText } from "../lib/format";
import { MOBILE_QUERY, useMedia } from "../lib/useMedia";

const PAGE_SIZE = 8;
const STATUS_OPTS: Option<string>[] = [
  { value: null, label: "Todos" },
  { value: "available", label: "Disponible" },
  { value: "processing", label: "En proceso" },
  { value: "error", label: "Error" },
  { value: "not_generated", label: "Sin generar" },
];

function LatestStrip({ summary }: { summary: ReportSummary }) {
  const row = summary.current;
  const generated =
    row.status === "processing" ? "En curso" : row.latest ? row.latest.generated_at_label : row.closing_label;
  return (
    <motion.section className="strip" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}>
      <div className="strip__facts">
        <div className="fact">
          <span className="fact__k">ÚLTIMO PERIODO</span>
          <span className="fact__v">{row.label}</span>
        </div>
        <div className="fact">
          <span className="fact__k">GENERADO</span>
          <span className="fact__v">{generated}</span>
        </div>
        <div className="fact">
          <span className="fact__k">VERSIÓN</span>
          <span className="fact__v">{row.latest && row.status !== "processing" ? `v${row.latest.version}` : "—"}</span>
        </div>
        <div className="fact">
          <span className="fact__k">ESTADO</span>
          <Estado status={row.status} />
        </div>
      </div>
      <div className="strip__action">
        <PeriodAction report={summary.key} row={row} label="Descargar último Excel" />
      </div>
    </motion.section>
  );
}

export default function ReportPage({ reportKey }: { reportKey: ReportKey }) {
  const isMobile = useMedia(MOBILE_QUERY);
  const [params, setParams] = useSearchParams();
  const [sheet, setSheet] = useState(false);
  const year = params.get("anio") ? Number(params.get("anio")) : null;
  const sub = params.get("periodo") ? Number(params.get("periodo")) : null;
  const status = params.get("estado");
  const sort = params.get("orden") ?? "period_desc";
  const page = Number(params.get("pagina") ?? "1") || 1;

  const summary = useReport(reportKey);
  const periods = usePeriods(reportKey, { year, sub, status, sort, page, page_size: PAGE_SIZE });

  const update = (patch: Record<string, string | number | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v === null || v === "" ? next.delete(k) : next.set(k, String(v))));
    if (!("pagina" in patch)) next.delete("pagina");
    setParams(next, { replace: true });
  };
  const clear = () => setParams(new URLSearchParams(sort !== "period_desc" ? { orden: sort } : {}), { replace: true });

  const data = periods.data;
  const kind = summary.data?.kind ?? (reportKey === "cortes" ? "month" : "quarter");
  const subName = kind === "month" ? "Mes" : "Periodo";
  const unit = data?.unit ?? (kind === "month" ? { singular: "mes", plural: "meses" } : { singular: "periodo", plural: "periodos" });
  const yearOpts: Option<number>[] = [{ value: null, label: "Todos" }, ...(data?.years ?? []).map((y) => ({ value: y, label: String(y) }))];
  const subOpts: Option<number>[] = [{ value: null, label: "Todos" }, ...(data?.sub_options ?? [])];
  const subLabel = subOpts.find((o) => o.value === sub)?.label;
  const statusLabel = STATUS_OPTS.find((o) => o.value === status)?.label;
  const chips = [
    year ? { key: "anio", label: `Año: ${year}`, onRemove: () => update({ anio: null }) } : null,
    sub ? { key: "periodo", label: `${subName}: ${subLabel}`, onRemove: () => update({ periodo: null }) } : null,
    status ? { key: "estado", label: `Estado: ${statusLabel}`, onRemove: () => update({ estado: null }) } : null,
  ].filter(Boolean) as { key: string; label: string; onRemove: () => void }[];
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const animKey = useMemo(() => JSON.stringify({ year, sub, status, sort, page }), [year, sub, status, sort, page]);

  const title = summary.data?.name ?? (reportKey === "cortes" ? "Cortes de suscripciones mensuales" : reportKey === "f6" ? "Reporte F6" : "Reporte T1.2");
  const frequency = summary.data?.frequency ?? (kind === "month" ? "Mensual" : "Trimestral");

  const desktopSelectors = (
    <>
      <Selector prefix="Año" value={year} options={yearOpts} onChange={(v) => update({ anio: v })} width={120} />
      <Selector prefix={subName} value={sub} options={subOpts} onChange={(v) => update({ periodo: v })} width={150} />
      <Selector prefix="Estado" value={status} options={STATUS_OPTS} onChange={(v) => update({ estado: v })} width={150} />
    </>
  );

  let body: JSX.Element;
  if (periods.isError) {
    body = (
      <div className="card-table">
        <EmptyState icon={emptyAlert} tone="error" title={`No se pudo cargar el listado de ${unit.plural}`}
          action={<RetryButton onClick={() => periods.refetch()} />}>
          Hubo un problema al consultar el servidor. Tus filtros se conservan; intenta de nuevo en unos segundos. Si
          persiste, avisa a soporte interno.
        </EmptyState>
      </div>
    );
  } else if (!data) {
    body = <div className="card-table"><SkeletonRows cols="periods" /></div>;
  } else if (data.items.length === 0 && chips.length > 0) {
    body = (
      <div className="card-table">
        <ActiveFilters chips={chips} onClear={clear} inline />
        <EmptyState icon={emptySearch} title={`No encontramos ${unit.plural} para los filtros seleccionados`}
          action={<SecondaryButton icon={btnX} label="Limpiar filtros" onClick={clear} />}>
          Prueba con otro año o estado, o limpia los filtros para ver todos los {unit.plural} del reporte.
        </EmptyState>
      </div>
    );
  } else if (data.items.length === 0) {
    body = (
      <div className="card-table">
        <EmptyState icon={emptyInbox} title={`Aún no hay ${unit.plural} generados para este reporte`}>
          Cuando el sistema genere el primer archivo aparecerá aquí con su periodo, fecha, versión y estado.
        </EmptyState>
      </div>
    );
  } else if (data.items.length === 1 && data.items[0].status === "pending" && data.total === 1) {
    const row = data.items[0];
    body = (
      <div className="card-table">
        <EmptyState icon={emptyHistory} title={`El periodo ${row.label} aún no se ha generado`}>
          El cierre es el {row.closing_label.replace("Cierre ", "")}. Mientras tanto puedes consultar y descargar los
          periodos anteriores.
        </EmptyState>
      </div>
    );
  } else {
    body = isMobile ? (
      <PeriodCards report={reportKey} rows={data.items} animKey={animKey} />
    ) : (
      <div className="card-table">
        <PeriodTable report={reportKey} kind={kind} rows={data.items} sort={sort}
          onSort={(s) => update({ orden: s === "period_desc" ? null : s })} animKey={animKey} />
      </div>
    );
  }

  return (
    <div className="stack-24">
      {!isMobile && <Breadcrumb current={title} />}
      {isMobile ? (
        <div className="mtitle">
          <h1 className="mtitle__h1">{title}</h1>
          <p className="mtitle__sub">
            {frequency} · {data ? countLabel(data.total, `${unit.singular} disponible`, `${unit.plural} disponibles`) : "…"}
          </p>
        </div>
      ) : (
        <PageTitle title={title} subtitle={`${frequency} · consulta un periodo y descarga el archivo Excel generado.`} />
      )}

      {!isMobile && summary.data && <LatestStrip summary={summary.data} />}

      {isMobile ? (
        <div className="mfilters">
          <Selector prefix="Año" value={year} options={yearOpts} onChange={(v) => update({ anio: v })} full />
          <button type="button" className="mfilters__btn" onClick={() => setSheet(true)}>
            <img src={sliders} alt="" width={16} height={16} />
            Filtros
            {(sub || status) && <span className="mfilters__dot" aria-label="Filtros activos" />}
          </button>
        </div>
      ) : (
        <div className="filters">
          <div className="filters__group">{desktopSelectors}</div>
          <span className="muted-13">{data ? countLabel(data.total, unit.singular, unit.plural) : " "}</span>
        </div>
      )}

      {!isMobile && !(data && data.items.length === 0 && chips.length > 0) && <ActiveFilters chips={chips} onClear={clear} />}

      {body}

      {data && data.total > 0 && (
        <div className="tfoot">
          <span className="muted-13">{showingText(data.page, data.page_size, data.total, unit.plural, isMobile)}</span>
          <Pagination id={`p-${reportKey}`} page={data.page} pages={pages} onPage={(p) => update({ pagina: p })} />
        </div>
      )}

      <FilterSheet open={sheet} onClose={() => setSheet(false)} onClear={clear}>
        <Selector prefix={subName} value={sub} options={subOpts} onChange={(v) => update({ periodo: v })} full />
        <Selector prefix="Estado" value={status} options={STATUS_OPTS} onChange={(v) => update({ estado: v })} full />
      </FilterSheet>
    </div>
  );
}
