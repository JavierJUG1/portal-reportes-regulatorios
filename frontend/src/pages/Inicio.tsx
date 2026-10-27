import { motion } from "framer-motion";
import { Link, useNavigate } from "react-router-dom";
import { useDashboard } from "../api/hooks";
import type { ReportSummary, Version } from "../api/types";
import cardFile from "../assets/figma/card-file.svg";
import cardFileMobile from "../assets/figma/card-file-mobile.svg";
import cardUsers from "../assets/figma/card-users.svg";
import cardUsersMobile from "../assets/figma/card-users-mobile.svg";
import emptyAlert from "../assets/figma/empty-alert.svg";
import emptyInbox from "../assets/figma/empty-inbox.svg";
import iconArrow from "../assets/figma/icon-arrow.svg";
import chevRight from "../assets/figma/icon-chevright-card.svg";
import { PeriodAction, VersionAction } from "../components/RowAction";
import { PageTitle } from "../components/Shell";
import { EmptyState, Estado, RetryButton, SecondaryButton } from "../components/ui";
import { generatedBy, REPORT_ROUTES } from "../lib/format";
import { reportsPhrase, useEnabledReports } from "../lib/reports";
import { MOBILE_QUERY, useMedia } from "../lib/useMedia";

const EASE = [0.22, 1, 0.36, 1] as const;

function generatedShort(r: ReportSummary): string {
  const row = r.current;
  if (row.status === "processing") return "En curso";
  if (!row.latest) return row.closing_label;
  return `${row.latest.generated_date_label} · v${row.latest.version}`;
}

function ReportCard({ r, index }: { r: ReportSummary; index: number }) {
  const navigate = useNavigate();
  const to = REPORT_ROUTES[r.key];
  return (
    <motion.article
      className="rcard"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, delay: index * 0.05, ease: EASE }}
      whileHover={{ y: -2 }}
    >
      <Link to={to} className="rcard__head">
        <span className="rcard__ic"><img src={r.icon === "users" ? cardUsers : cardFile} alt="" width={20} height={20} /></span>
        <span className="stack stack--2 grow">
          <span className="rcard__title">{r.name}</span>
          <span className="sub-13">{r.frequency}</span>
        </span>
        <img src={chevRight} alt="" width={18} height={18} className="rcard__chev" />
      </Link>
      <dl className="rcard__info">
        <div className="rcard__row"><dt>Último periodo</dt><dd>{r.current.label}</dd></div>
        <div className="rcard__row"><dt>Generado</dt><dd>{generatedShort(r)}</dd></div>
        <div className="rcard__row"><dt>Estado</dt><dd><Estado status={r.current.status} /></dd></div>
      </dl>
      <div className="rcard__actions">
        <div className="grow rcard__primary"><PeriodAction report={r.key} row={r.current} full /></div>
        <SecondaryButton label="Ver periodos" onClick={() => navigate(to)} />
      </div>
    </motion.article>
  );
}

function ReportCardMobile({ r, index }: { r: ReportSummary; index: number }) {
  const row = r.current;
  const sub =
    row.status === "processing"
      ? `${row.label} · generando`
      : row.latest
        ? `${row.label} · v${row.latest.version} · ${row.latest.generated_date_label.split(" ").slice(0, 2).join(" ")}`
        : `${row.label} · sin generar`;
  return (
    <motion.article className="rcard rcard--m" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, delay: index * 0.05, ease: EASE }}>
      <Link to={REPORT_ROUTES[r.key]} className="rcard__head">
        <span className="rcard__ic rcard__ic--m">
          <img src={r.icon === "users" ? cardUsersMobile : cardFileMobile} alt="" width={18} height={18} />
        </span>
        <span className="stack stack--2 grow">
          <span className="rcard__title rcard__title--m">{r.name}</span>
          <span className="sub-12">{sub}</span>
        </span>
        <img src={chevRight} alt="" width={18} height={18} />
      </Link>
      <div className="rcard__foot">
        <Estado status={row.status} />
        <PeriodAction report={r.key} row={row} />
      </div>
    </motion.article>
  );
}

function ActivityRow({ v, index }: { v: Version; index: number }) {
  const when =
    v.status === "processing" ? "Generación en curso" : `${v.generated_at_label} · ${generatedBy(v, true)}`;
  return (
    <motion.div className="arow" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      transition={{ duration: 0.2, delay: 0.1 + index * 0.03 }}>
      <span className="stack stack--2 grow arow__main">
        <span className="cell-title">{v.report_name}</span>
        <span className="sub-12">{v.period_label}{v.status !== "processing" ? ` · v${v.version}` : ""}</span>
      </span>
      <span className="arow__when sub-13">{when}</span>
      <span className="arow__estado"><Estado status={v.status} /></span>
      <span className="arow__accion"><VersionAction v={v} /></span>
    </motion.div>
  );
}

export default function Inicio() {
  const isMobile = useMedia(MOBILE_QUERY);
  const { data, isError, refetch } = useDashboard();
  const enabled = useEnabledReports();
  const subtitle = `Consulta los periodos disponibles y descarga en Excel ${reportsPhrase(enabled)}.`;

  if (isError) {
    return (
      <div className="stack-24">
        <PageTitle title="Portal de reportes" subtitle={subtitle} />
        <div className="card-table">
          <EmptyState icon={emptyAlert} tone="error" title="No se pudo cargar la información" action={<RetryButton onClick={() => refetch()} />}>
            Hubo un problema al consultar el servidor. Intenta de nuevo en unos segundos. Si persiste, avisa a soporte interno.
          </EmptyState>
        </div>
      </div>
    );
  }

  if (isMobile) {
    return (
      <div className="stack-16">
        <h1 className="mtitle__h1 mtitle__h1--home">Portal de reportes</h1>
        <p className="mhome__sub">Consulta los periodos y descarga en Excel {reportsPhrase(enabled)}.</p>
        {data ? data.reports.map((r, i) => <ReportCardMobile key={r.key} r={r} index={i} />) : <div className="rcard rcard--m sk-card" />}
      </div>
    );
  }

  return (
    <div className="stack-24">
      <PageTitle title="Portal de reportes" subtitle={subtitle} />
      <div className="rcards">
        {data
          ? data.reports.map((r, i) => <ReportCard key={r.key} r={r} index={i} />)
          : enabled.map((k) => <div key={k} className="rcard sk-card" />)}
      </div>
      <motion.section className="activity" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.24, delay: 0.12, ease: EASE }}>
        <div className="activity__head">
          <h2 className="activity__title">Actividad reciente</h2>
          <Link to="/historial" className="activity__link">
            Ver historial completo
            <img src={iconArrow} alt="" width={14} height={14} />
          </Link>
        </div>
        {data && data.recent.length === 0 && (
          <EmptyState icon={emptyInbox} title="Aún no hay generaciones registradas">
            Cuando el sistema genere el primer archivo aparecerá aquí con su periodo, fecha, versión y estado.
          </EmptyState>
        )}
        {data?.recent.map((v, i) => <ActivityRow key={v.id} v={v} index={i} />)}
      </motion.section>
    </div>
  );
}
