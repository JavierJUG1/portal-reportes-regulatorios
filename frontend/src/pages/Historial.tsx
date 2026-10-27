import { motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useHistory } from "../api/hooks";
import type { ReportKey, Version } from "../api/types";
import btnX from "../assets/figma/btn-x.svg";
import emptyAlert from "../assets/figma/empty-alert.svg";
import emptyInbox from "../assets/figma/empty-inbox.svg";
import emptySearch from "../assets/figma/empty-search.svg";
import rowFile from "../assets/figma/row-file.svg";
import sliders from "../assets/figma/icon-sliders.svg";
import rowUsers from "../assets/figma/row-users.svg";
import { FilterSheet } from "../components/FilterSheet";
import { SortHeader } from "../components/PeriodTable";
import { VersionAction } from "../components/RowAction";
import { Breadcrumb, PageTitle } from "../components/Shell";
import {
  ActiveFilters, EmptyState, Estado, Pagination, RetryButton, SearchInput, SecondaryButton, Selector, SkeletonRows,
  type Option,
} from "../components/ui";
import { countLabel, generatedBy, showingText } from "../lib/format";
import { reportsPhrase, useEnabledReports } from "../lib/reports";
import { MOBILE_QUERY, useMedia } from "../lib/useMedia";

const EASE = [0.22, 1, 0.36, 1] as const;
const PAGE_SIZE = 8;
const REPORT_OPTS: Option<string>[] = [
  { value: null, label: "Todos" },
  { value: "f6", label: "Reporte F6" },
  { value: "t12", label: "Reporte T1.2" },
  { value: "cortes", label: "Cortes de suscripciones" },
];
const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
const SUB_OPTS: Option<string>[] = [
  { value: null, label: "Todos" },
  ...[1, 2, 3, 4].map((n) => ({ value: `T${n}`, label: `Trimestre ${n}` })),
  ...MESES.map((m, i) => ({ value: `M${i + 1}`, label: m })),
];
const STATUS_OPTS: Option<string>[] = [
  { value: null, label: "Todos" },
  { value: "available", label: "Disponible" },
  { value: "processing", label: "En proceso" },
  { value: "error", label: "Error" },
];

function Tag({ tag }: { tag: Version["tag"] }) {
  if (tag === "vigente") return <span className="vtag vtag--on">Vigente</span>;
  if (tag === "reemplazada") return <span className="vtag">Reemplazada</span>;
  return null;
}

function ReportIcon({ v }: { v: Version }) {
  return v.report === "cortes"
    ? <img src={rowUsers} alt="" width={16} height={16} />
    : <img src={rowFile} alt="" width={16} height={16} />;
}

export default function Historial() {
  const isMobile = useMedia(MOBILE_QUERY);
  const enabled = useEnabledReports();
  const reportOpts = REPORT_OPTS.filter((o) => o.value === null || enabled.includes(o.value as ReportKey));
  // Los meses solo aplican si hay un reporte mensual habilitado (cortes de suscripciones).
  const subOpts = enabled.includes("cortes") ? SUB_OPTS : SUB_OPTS.filter((o) => !String(o.value).startsWith("M"));
  const [params, setParams] = useSearchParams();
  const [sheet, setSheet] = useState(false);
  const q = params.get("q") ?? "";
  const [search, setSearch] = useState(q);
  const report = params.get("reporte");
  const year = params.get("anio") ? Number(params.get("anio")) : null;
  const sub = params.get("periodo");
  const status = params.get("estado");
  const sort = params.get("orden") ?? "generated_desc";
  const page = Number(params.get("pagina") ?? "1") || 1;

  const update = (patch: Record<string, string | number | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v === null || v === "" ? next.delete(k) : next.set(k, String(v))));
    if (!("pagina" in patch)) next.delete("pagina");
    setParams(next, { replace: true });
  };
  // Búsqueda con pequeño retardo para no consultar en cada tecla.
  useEffect(() => {
    const t = setTimeout(() => {
      if (search !== q) update({ q: search.trim() || null });
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const history = useHistory({ q, report, year, sub, status, sort, page, page_size: PAGE_SIZE });
  const data = history.data;
  const clear = () => {
    setSearch("");
    setParams(new URLSearchParams(), { replace: true });
  };
  const yearOpts: Option<number>[] = [{ value: null, label: "Todos" }, ...(data?.years ?? []).map((y) => ({ value: y, label: String(y) }))];
  const chips = [
    q ? { key: "q", label: `Búsqueda: ${q}`, onRemove: () => { setSearch(""); update({ q: null }); } } : null,
    report ? { key: "reporte", label: `Reporte: ${reportOpts.find((o) => o.value === report)?.label}`, onRemove: () => update({ reporte: null }) } : null,
    year ? { key: "anio", label: `Año: ${year}`, onRemove: () => update({ anio: null }) } : null,
    sub ? { key: "periodo", label: `Periodo: ${subOpts.find((o) => o.value === sub)?.label}`, onRemove: () => update({ periodo: null }) } : null,
    status ? { key: "estado", label: `Estado: ${STATUS_OPTS.find((o) => o.value === status)?.label}`, onRemove: () => update({ estado: null }) } : null,
  ].filter(Boolean) as { key: string; label: string; onRemove: () => void }[];
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const animKey = useMemo(() => JSON.stringify({ q, report, year, sub, status, sort, page }), [q, report, year, sub, status, sort, page]);

  let body: JSX.Element;
  if (history.isError) {
    body = (
      <div className="card-table">
        <EmptyState icon={emptyAlert} tone="error" title="No se pudo cargar el historial" action={<RetryButton onClick={() => history.refetch()} />}>
          Hubo un problema al consultar el servidor. Tus filtros se conservan; intenta de nuevo en unos segundos. Si persiste, avisa a soporte interno.
        </EmptyState>
      </div>
    );
  } else if (!data) {
    body = <div className="card-table"><SkeletonRows cols="history" /></div>;
  } else if (data.items.length === 0) {
    body = (
      <div className="card-table">
        {chips.length > 0 ? (
          <EmptyState icon={emptySearch} title="No encontramos versiones para los filtros seleccionados"
            action={<SecondaryButton icon={btnX} label="Limpiar filtros" onClick={clear} />}>
            Prueba con otro año, reporte o estado, o limpia los filtros para ver todas las versiones.
          </EmptyState>
        ) : (
          <EmptyState icon={emptyInbox} title="Aún no hay versiones generadas">
            Cuando el sistema genere el primer archivo aparecerá aquí con su periodo, fecha, versión y estado.
          </EmptyState>
        )}
      </div>
    );
  } else if (isMobile) {
    body = (
      <div className="pcards" key={animKey}>
        {data.items.map((v, i) => (
          <motion.article key={v.id} className={`pcard ${v.tag === "reemplazada" ? "pcard--alt" : ""}`}
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, delay: Math.min(i * 0.03, 0.2), ease: EASE }}>
            <div className="pcard__head">
              <span className="stack stack--3">
                <span className="pcard__title">{v.report_name}</span>
                <span className="sub-12">{v.period_label}{v.quarter ? ` · Trimestre ${v.quarter.number}` : ""}</span>
              </span>
              <Estado status={v.status} />
            </div>
            <div className="pcard__meta">
              <span className="kv"><span className="kv__k">GENERADO</span><span className="kv__v">{v.status === "processing" ? "En curso" : v.generated_date_label}</span></span>
              <span className="kv"><span className="kv__k">VERSIÓN</span><span className="kv__v kv__v--tag">v{v.version} <Tag tag={v.tag} /></span></span>
            </div>
            <VersionAction v={v} full />
          </motion.article>
        ))}
      </div>
    );
  } else {
    body = (
      <div className="card-table">
        <div className="table" role="table" aria-label="Historial de versiones">
          <div className="thead trow cols-history" role="row">
            <div className="cell cell--main"><span className="th">REPORTE</span></div>
            <SortHeader label="PERIODO" field="period" sort={sort} onSort={(s) => update({ orden: s })} className="cell--per" />
            <div className="cell cell--ver"><span className="th">VERSIÓN</span></div>
            <SortHeader label="GENERADO" field="generated" sort={sort} onSort={(s) => update({ orden: s === "generated_desc" ? null : s })} className="cell--gen" />
            <div className="cell cell--estado"><span className="th">ESTADO</span></div>
            <div className="cell cell--accion"><span className="th">ACCIÓN</span></div>
          </div>
          <div key={animKey}>
            {data.items.map((v, i) => (
              <motion.div key={v.id} className={`trow cols-history ${v.tag === "reemplazada" ? "trow--alt" : ""}`} role="row"
                initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, delay: Math.min(i * 0.025, 0.2), ease: EASE }}>
                <div className="cell cell--main">
                  <span className="row-ic"><ReportIcon v={v} /></span>
                  <span className="cell-title ellipsis" title={v.filename ?? v.report_name}>
                    <span className="report-name-full">{v.report_name}</span>
                    <span className="report-name-short">{v.report_short}</span>
                  </span>
                </div>
                <div className="cell cell--per">
                  {v.quarter ? (
                    <span className="stack">
                      <span className="cell-strong-14">{v.period_label}</span>
                      <span className="sub-12">Trimestre {v.quarter.number} · mes {v.quarter.mes_trim}</span>
                    </span>
                  ) : (
                    <span className="cell-strong-14">{v.period_label}</span>
                  )}
                </div>
                <div className="cell cell--ver"><span className="ver"><span className="ver__n">v{v.version}</span><Tag tag={v.tag} /></span></div>
                <div className="cell cell--gen">
                  {v.status === "processing" ? (
                    <span className="cell-strong-14">En curso</span>
                  ) : (
                    <span className="stack">
                      <span className="cell-strong-14">{v.generated_at_label}</span>
                      <span className="sub-12">{generatedBy(v)}</span>
                    </span>
                  )}
                </div>
                <div className="cell cell--estado"><Estado status={v.status} /></div>
                <div className="cell cell--accion"><VersionAction v={v} /></div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="stack-24">
      {!isMobile && <Breadcrumb current="Historial" />}
      {isMobile ? (
        <div className="mtitle">
          <h1 className="mtitle__h1">Historial de versiones</h1>
          <p className="mtitle__sub">{data ? countLabel(data.total, "versión", "versiones") : "…"}</p>
        </div>
      ) : (
        <PageTitle title="Historial de versiones"
          subtitle={`Todas las versiones generadas de ${reportsPhrase(enabled)}, de la más reciente a la más antigua. Las versiones anteriores se conservan.`} />
      )}

      {isMobile ? (
        <>
          <SearchInput value={search} onChange={setSearch} />
          <div className="mfilters">
            <Selector prefix="Año" value={year} options={yearOpts} onChange={(v) => update({ anio: v })} full />
            <button type="button" className="mfilters__btn" onClick={() => setSheet(true)}>
              <img src={sliders} alt="" width={16} height={16} />
              Filtros
              {(report || sub || status) && <span className="mfilters__dot" aria-label="Filtros activos" />}
            </button>
          </div>
        </>
      ) : (
        <div className="filters">
          <div className="filters__group">
            <SearchInput value={search} onChange={setSearch} />
            <Selector prefix="Reporte" value={report} options={reportOpts} onChange={(v) => update({ reporte: v })} width={150} />
            <Selector prefix="Año" value={year} options={yearOpts} onChange={(v) => update({ anio: v })} width={120} />
            <Selector prefix="Periodo" value={sub} options={subOpts} onChange={(v) => update({ periodo: v })} width={150} />
            <Selector prefix="Estado" value={status} options={STATUS_OPTS} onChange={(v) => update({ estado: v })} width={150} />
          </div>
          <span className="muted-13">{data ? countLabel(data.total, "versión", "versiones") : " "}</span>
        </div>
      )}

      {!isMobile && <ActiveFilters chips={chips} onClear={clear} />}
      {body}
      {data && data.total > 0 && (
        <div className="tfoot">
          <span className="muted-13">{showingText(data.page, data.page_size, data.total, "versiones", isMobile)}</span>
          <Pagination id="historial" page={data.page} pages={pages} onPage={(p) => update({ pagina: p })} />
        </div>
      )}
      <FilterSheet open={sheet} onClose={() => setSheet(false)} onClear={clear}>
        <Selector prefix="Reporte" value={report} options={reportOpts} onChange={(v) => update({ reporte: v })} full />
        <Selector prefix="Periodo" value={sub} options={subOpts} onChange={(v) => update({ periodo: v })} full />
        <Selector prefix="Estado" value={status} options={STATUS_OPTS} onChange={(v) => update({ estado: v })} full />
      </FilterSheet>
    </div>
  );
}
