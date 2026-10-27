import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { RowStatus } from "../api/types";
import btnDownload from "../assets/figma/btn-download.svg";
import btnLoader from "../assets/figma/btn-loader.svg";
import btnRefresh from "../assets/figma/btn-refresh.svg";
import chipX from "../assets/figma/chip-x.svg";
import estadoAlert from "../assets/figma/estado-alert.svg";
import estadoCheck from "../assets/figma/estado-check.svg";
import estadoInfo from "../assets/figma/estado-info.svg";
import estadoLoader from "../assets/figma/estado-loader.svg";
import iconSearch from "../assets/figma/icon-search.svg";
import pagLeft from "../assets/figma/pag-chevleft.svg";
import pagRight from "../assets/figma/pag-chevright.svg";
import selectorChev from "../assets/figma/selector-chevdown.svg";

const EASE = [0.22, 1, 0.36, 1] as const;

/* ------------------------------------------------------------------ Estado */
const ESTADOS: Record<string, { label: string; icon: string; cls: string }> = {
  available: { label: "Disponible", icon: estadoCheck, cls: "estado--ok" },
  processing: { label: "En proceso", icon: estadoLoader, cls: "estado--proc" },
  error: { label: "Error", icon: estadoAlert, cls: "estado--error" },
  not_generated: { label: "Sin generar", icon: estadoInfo, cls: "estado--none" },
  pending: { label: "Sin generar", icon: estadoInfo, cls: "estado--none" },
};

export function Estado({ status }: { status: RowStatus }) {
  const e = ESTADOS[status] ?? ESTADOS.not_generated;
  return (
    <AnimatePresence mode="popLayout" initial={false}>
      <motion.span
        key={e.label}
        className={`estado ${e.cls}`}
        initial={{ opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.92 }}
        transition={{ duration: 0.18, ease: EASE }}
      >
        <img src={e.icon} alt="" width={13} height={13} className={status === "processing" ? "spin" : undefined} />
        {e.label}
      </motion.span>
    </AnimatePresence>
  );
}

/* ----------------------------------------------------------------- Botones */
interface BtnProps {
  onClick?: () => void;
  full?: boolean;
  label?: string;
  className?: string;
  title?: string;
}

export function DownloadButton({ busy, onClick, full, label = "Descargar Excel", className = "" }: BtnProps & { busy?: boolean }) {
  return (
    <motion.button
      type="button"
      layout
      className={`btn btn--primary ${full ? "btn--full" : ""} ${busy ? "is-busy" : ""} ${className}`}
      onClick={busy ? undefined : onClick}
      disabled={busy}
      aria-busy={busy}
      whileTap={busy ? undefined : { scale: 0.97 }}
      transition={{ duration: 0.18, ease: EASE }}
    >
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={busy ? "busy" : "idle"}
          className="btn__inner"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.16, ease: EASE }}
        >
          <img src={busy ? btnLoader : btnDownload} alt="" width={16} height={16} className={busy ? "spin" : undefined} />
          {busy ? "Preparando…" : label}
        </motion.span>
      </AnimatePresence>
    </motion.button>
  );
}

export function RetryButton({ onClick, full, busy }: BtnProps & { busy?: boolean }) {
  if (busy) return <DownloadButton busy full={full} />;
  return (
    <motion.button type="button" layout className={`btn btn--outline ${full ? "btn--full" : ""}`} onClick={onClick}
      whileTap={{ scale: 0.97 }}>
      <span className="btn__inner">
        <img src={btnRefresh} alt="" width={16} height={16} />
        Reintentar
      </span>
    </motion.button>
  );
}

export function SecondaryButton({ onClick, label, icon, full, className = "", title }: BtnProps & { icon?: string }) {
  return (
    <motion.button type="button" className={`btn btn--outline ${full ? "btn--full" : ""} ${className}`} onClick={onClick}
      whileTap={{ scale: 0.97 }} title={title}>
      <span className="btn__inner">
        {icon && <img src={icon} alt="" width={16} height={16} />}
        {label}
      </span>
    </motion.button>
  );
}

export function IconButton({ onClick, icon, label }: { onClick?: () => void; icon: string; label: string }) {
  return (
    <motion.button type="button" className="icon-btn" onClick={onClick} aria-label={label} title={label}
      whileTap={{ scale: 0.92 }}>
      <img src={icon} alt="" width={16} height={16} />
    </motion.button>
  );
}

/* ---------------------------------------------------------------- Selector */
export interface Option<T extends string | number> {
  value: T | null;
  label: string;
}

export function Selector<T extends string | number>({
  prefix, value, options, onChange, width, full,
}: {
  prefix: string;
  value: T | null;
  options: Option<T>[];
  onChange: (v: T | null) => void;
  width?: number;
  full?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const listId = useId();
  const current = options.find((o) => o.value === value) ?? options[0];
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div className={`selector ${full ? "selector--full" : ""}`} ref={ref} style={width && !full ? { width } : undefined}>
      <button
        type="button"
        className={`selector__btn ${open ? "is-open" : ""} ${value !== null ? "has-value" : ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="selector__text">
          {prefix}: {current?.label ?? "Todos"}
        </span>
        <motion.img src={selectorChev} alt="" width={16} height={16} animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.18 }} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.ul
            id={listId}
            role="listbox"
            className="selector__menu"
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98, transition: { duration: 0.12 } }}
            transition={{ duration: 0.18, ease: EASE }}
          >
            {options.map((o) => (
              <li key={String(o.value)} role="option" aria-selected={o.value === value}>
                <button
                  type="button"
                  className={`selector__opt ${o.value === value ? "is-selected" : ""}`}
                  onClick={() => {
                    onChange(o.value);
                    setOpen(false);
                  }}
                >
                  {o.label}
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ---------------------------------------------------------------- Búsqueda */
export function SearchInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label className="search">
      <img src={iconSearch} alt="" width={18} height={18} />
      <input
        type="search"
        value={value}
        placeholder="Buscar por nombre o código…"
        onChange={(e) => onChange(e.target.value)}
        aria-label="Buscar por nombre o código"
      />
    </label>
  );
}

/* -------------------------------------------------------------- Chip filtro */
export function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <motion.span
      layout
      className="chip"
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ duration: 0.16, ease: EASE }}
    >
      {label}
      <button type="button" className="chip__x" onClick={onRemove} aria-label={`Quitar filtro ${label}`}>
        <img src={chipX} alt="" width={12} height={12} />
      </button>
    </motion.span>
  );
}

export function ActiveFilters({ chips, onClear, inline }: {
  chips: { key: string; label: string; onRemove: () => void }[];
  onClear: () => void;
  inline?: boolean;
}) {
  return (
    <AnimatePresence initial={false}>
      {chips.length > 0 && (
        <motion.div
          className={`active-filters ${inline ? "active-filters--inline" : ""}`}
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.18, ease: EASE }}
        >
          <span className="active-filters__label">Filtros activos:</span>
          <AnimatePresence initial={false}>
            {chips.map((c) => (
              <Chip key={c.key} label={c.label} onRemove={c.onRemove} />
            ))}
          </AnimatePresence>
          <button type="button" className="link-btn" onClick={onClear}>
            Limpiar todo
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* --------------------------------------------------------------- Paginación */
function pageList(page: number, pages: number): (number | "…")[] {
  if (pages <= 5) return Array.from({ length: pages }, (_, i) => i + 1);
  const set = new Set([1, 2, 3, page - 1, page, page + 1, pages].filter((p) => p >= 1 && p <= pages));
  const sorted = [...set].sort((a, b) => a - b);
  const out: (number | "…")[] = [];
  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) out.push("…");
    out.push(p);
  });
  return out;
}

export function Pagination({ page, pages, onPage, id }: { page: number; pages: number; onPage: (p: number) => void; id: string }) {
  if (pages <= 1) return null;
  return (
    <nav className="pagination" aria-label="Paginación">
      <button type="button" className="pag" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Página anterior">
        <img src={pagLeft} alt="" width={16} height={16} />
      </button>
      {pageList(page, pages).map((p, i) =>
        p === "…" ? (
          <span key={`e${i}`} className="pag__ellipsis">…</span>
        ) : (
          <button key={p} type="button" className={`pag ${p === page ? "is-active" : ""}`} onClick={() => onPage(p)}
            aria-current={p === page ? "page" : undefined}>
            {p === page && <motion.span layoutId={`pag-${id}`} className="pag__bg" transition={{ duration: 0.2, ease: EASE }} />}
            <span className="pag__num">{p}</span>
          </button>
        ),
      )}
      <button type="button" className="pag" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Página siguiente">
        <img src={pagRight} alt="" width={16} height={16} />
      </button>
    </nav>
  );
}

/* ---------------------------------------------------------- Estados vacíos */
export function EmptyState({ icon, title, children, action, tone = "neutral" }: {
  icon: string;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  tone?: "neutral" | "error";
}) {
  return (
    <motion.div className="empty" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: EASE }}>
      <span className={`empty__ic ${tone === "error" ? "empty__ic--error" : ""}`}>
        <img src={icon} alt="" width={24} height={24} />
      </span>
      <p className="empty__title">{title}</p>
      {children && <p className="empty__text">{children}</p>}
      {action && <div className="empty__action">{action}</div>}
    </motion.div>
  );
}

export function SkeletonRows({ rows = 4, cols }: { rows?: number; cols: "periods" | "history" }) {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Cargando">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={`trow trow--skel ${cols === "history" ? "cols-history" : "cols-periods"}`}>
          <div className="cell cell--main">
            <span className="sk sk--box" />
            <span className="sk-stack">
              <span className="sk" style={{ width: 160, height: 12 }} />
              <span className="sk" style={{ width: 120, height: 10 }} />
            </span>
          </div>
          <div className="cell cell--gen">
            <span className="sk-stack">
              <span className="sk" style={{ width: 130, height: 12 }} />
              <span className="sk" style={{ width: 80, height: 10 }} />
            </span>
          </div>
          <div className="cell cell--ver"><span className="sk" style={{ width: 28, height: 12 }} /></div>
          <div className="cell cell--estado"><span className="sk sk--pill" style={{ width: 90, height: 22 }} /></div>
          <div className="cell cell--accion"><span className="sk sk--pill" style={{ width: 142, height: 34 }} /></div>
        </div>
      ))}
    </div>
  );
}

export { pageList };
