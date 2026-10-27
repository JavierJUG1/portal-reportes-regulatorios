import { useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api/client";
import { useAuthConfig, useMe, useMeta } from "./api/hooks";
import logo from "./assets/figma/logo-giga.png";
import { AppShell } from "./components/Shell";
import { ActionsProvider } from "./lib/actions";
import { useEnabledReports } from "./lib/reports";
import Historial from "./pages/Historial";
import Inicio from "./pages/Inicio";
import Login from "./pages/Login";
import ReportPage from "./pages/ReportPage";

function Splash() {
  return (
    <div className="splash">
      <motion.img src={logo} alt="GIGA+ Fibra" width={88} height={28} initial={{ opacity: 0 }} animate={{ opacity: [0.4, 1, 0.4] }}
        transition={{ duration: 1.6, repeat: Infinity }} />
    </div>
  );
}

function Protected() {
  const me = useMe();
  const meta = useMeta();
  const cfg = useAuthConfig();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const enabled = useEnabledReports();

  useEffect(() => {
    const onUnauthorized = () => qc.invalidateQueries({ queryKey: ["me"] });
    window.addEventListener("portal:unauthorized", onUnauthorized);
    return () => window.removeEventListener("portal:unauthorized", onUnauthorized);
  }, [qc]);

  if (me.isLoading) return <Splash />;
  if (me.isError || !me.data) {
    const next = location.pathname + location.search;
    return <Navigate to={`/login${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`} replace />;
  }
  // Las rutas de reportes dependen de ENABLED_REPORTS: se espera a conocerlas para no redirigir un enlace directo.
  if (meta.isPending) return <Splash />;

  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    qc.clear();
    navigate("/login?salir=1", { replace: true });
  };

  return (
    <ActionsProvider>
      <AppShell user={me.data} envLabel={meta.data?.env_label ?? cfg.data?.env_label ?? ""}
        lastSync={meta.data?.last_sync_label ?? null} onLogout={logout}>
        <Routes location={location}>
          <Route path="/" element={<Inicio />} />
          {enabled.map((key) => (
            <Route key={key} path={`/reportes/${key}`} element={<ReportPage key={key} reportKey={key} />} />
          ))}
          <Route path="/historial" element={<Historial />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </ActionsProvider>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/*" element={<Protected />} />
    </Routes>
  );
}
