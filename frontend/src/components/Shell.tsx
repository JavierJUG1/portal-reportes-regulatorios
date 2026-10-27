import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import type { ReportKey, User } from "../api/types";
import { useEnabledReports } from "../lib/reports";
import headerChev from "../assets/figma/icon-chevdown-header.svg";
import iconMenu from "../assets/figma/icon-menu.svg";
import drawerX from "../assets/figma/icon-x-drawer.svg";
import logo from "../assets/figma/logo-giga.png";
import navFileActive from "../assets/figma/nav-file-active.svg";
import navFile from "../assets/figma/nav-file.svg";
import navHistoryActive from "../assets/figma/nav-history-active.svg";
import navHistory from "../assets/figma/nav-history.svg";
import navHomeActive from "../assets/figma/nav-home-active.svg";
import navHome from "../assets/figma/nav-home.svg";
import navUsersActive from "../assets/figma/nav-users-active.svg";
import navUsers from "../assets/figma/nav-users.svg";

const EASE = [0.22, 1, 0.36, 1] as const;

interface NavEntry {
  to: string;
  label: string;
  icon: string;
  iconActive: string;
  end?: boolean;
  report?: ReportKey;
}

const NAV: { group: string; items: NavEntry[] }[] = [
  {
    group: "CONSULTA Y DESCARGA",
    items: [
      { to: "/", label: "Inicio", icon: navHome, iconActive: navHomeActive, end: true },
      { to: "/reportes/f6", label: "Reporte F6", icon: navFile, iconActive: navFileActive, report: "f6" },
      { to: "/reportes/t12", label: "Reporte T1.2", icon: navFile, iconActive: navFileActive, report: "t12" },
      { to: "/reportes/cortes", label: "Cortes de suscripciones", icon: navUsers, iconActive: navUsersActive, report: "cortes" },
    ],
  },
  { group: "VERSIONES", items: [{ to: "/historial", label: "Historial", icon: navHistory, iconActive: navHistoryActive }] },
];

function NavItems({ layoutGroup, onNavigate, mobile }: { layoutGroup: string; onNavigate?: () => void; mobile?: boolean }) {
  const enabled = useEnabledReports();
  const groups = NAV.map((g) => ({ ...g, items: g.items.filter((it) => !it.report || enabled.includes(it.report)) }));
  return (
    <>
      {groups.map((g) => (
        <div key={g.group} className="nav-group">
          <p className="nav-group__label">{g.group}</p>
          {g.items.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              end={it.end ?? false}
              onClick={onNavigate}
              className={({ isActive }) => `nav-item ${mobile ? "nav-item--mobile" : ""} ${isActive ? "is-active" : ""}`}
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <motion.span layoutId={`nav-pill-${layoutGroup}`} className="nav-item__pill"
                      transition={{ duration: 0.22, ease: EASE }} />
                  )}
                  <img src={isActive ? it.iconActive : it.icon} alt="" width={18} height={18} />
                  <span className="nav-item__label">{it.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </div>
      ))}
    </>
  );
}

function UserMenu({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div className="user" ref={ref}>
      <button type="button" className="user__btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="avatar">{user.initials}</span>
        <span className="user__meta">
          <span className="user__name">{user.name}</span>
          <span className="user__role">{user.role_label}</span>
        </span>
        <motion.img src={headerChev} alt="" width={16} height={16} animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.18 }} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            className="user__menu"
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98, transition: { duration: 0.12 } }}
            transition={{ duration: 0.18, ease: EASE }}
          >
            <div className="user__menu-head">
              <span className="user__menu-name">{user.name}</span>
              <span className="user__menu-mail">{user.email}</span>
              <span className={`user__menu-perm ${user.can_generate ? "is-on" : ""}`}>
                {user.can_generate ? "System Manager · genera reportes" : "Consulta y descarga"}
              </span>
            </div>
            <button type="button" role="menuitem" className="user__menu-item" onClick={onLogout}>
              Cerrar sesión
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function AppShell({ user, envLabel, lastSync, onLogout, children }: {
  user: User;
  envLabel: string;
  lastSync: string | null;
  onLogout: () => void;
  children: ReactNode;
}) {
  const [drawer, setDrawer] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => setDrawer(false), [location.pathname]);
  useEffect(() => {
    document.body.style.overflow = drawer ? "hidden" : "";
  }, [drawer]);

  return (
    <div className="app">
      {/* Encabezado escritorio */}
      <header className="header">
        <div className="header__brand">
          <button type="button" className="header__logo" onClick={() => navigate("/")} aria-label="Ir al inicio">
            <img src={logo} alt="GIGA+ Fibra" width={88} height={28} />
          </button>
          <span className="header__divider" aria-hidden />
          <span className="header__title">Portal de reportes</span>
          <span className="header__env">{envLabel}</span>
        </div>
        <UserMenu user={user} onLogout={onLogout} />
      </header>

      {/* Encabezado móvil */}
      <header className="mheader">
        <div className="mheader__left">
          <button type="button" className="mheader__menu" aria-label="Abrir menú" onClick={() => setDrawer(true)}>
            <img src={iconMenu} alt="" width={22} height={22} />
          </button>
          <img src={logo} alt="GIGA+ Fibra" width={76} height={24} className="mheader__logo" />
        </div>
        <span className="avatar avatar--sm">{user.initials}</span>
      </header>

      <div className="body">
        <aside className="sidebar" aria-label="Navegación principal">
          <nav className="sidebar__nav">
            <NavItems layoutGroup="desk" />
          </nav>
          {lastSync && (
            <div className="sync">
              <span className="sync__label">Última sincronización</span>
              <span className="sync__value">{lastSync}</span>
            </div>
          )}
        </aside>
        <main className="content">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              className="page"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.18, ease: EASE }}
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* Menú lateral móvil */}
      <AnimatePresence>
        {drawer && (
          <>
            <motion.div className="overlay" onClick={() => setDrawer(false)} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              exit={{ opacity: 0 }} transition={{ duration: 0.2 }} />
            <motion.aside
              className="drawer"
              role="dialog"
              aria-modal="true"
              aria-label="Menú"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ duration: 0.24, ease: EASE }}
            >
              <div className="drawer__head">
                <span className="drawer__title">Portal de reportes</span>
                <button type="button" className="drawer__close" aria-label="Cerrar menú" onClick={() => setDrawer(false)}>
                  <img src={drawerX} alt="" width={20} height={20} />
                </button>
              </div>
              <nav className="drawer__nav">
                <NavItems layoutGroup="mobile" mobile onNavigate={() => setDrawer(false)} />
              </nav>
              <div className="drawer__user">
                <span className="avatar">{user.initials}</span>
                <span className="drawer__user-meta">
                  <span className="drawer__user-name">{user.name}</span>
                  <button type="button" className="drawer__logout" onClick={onLogout}>
                    Cerrar sesión
                  </button>
                </span>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

export function Breadcrumb({ current }: { current: string }) {
  return (
    <nav className="crumbs" aria-label="Migas de pan">
      <NavLink to="/" className="crumbs__link">Inicio</NavLink>
      <span className="crumbs__sep" aria-hidden>›</span>
      <span className="crumbs__current" aria-current="page">{current}</span>
    </nav>
  );
}

export function PageTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="ptitle">
      <h1 className="ptitle__h1">{title}</h1>
      <p className="ptitle__sub">{subtitle}</p>
    </div>
  );
}
