import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuthConfig } from "../api/hooks";
import type { User } from "../api/types";
import btnLoader from "../assets/figma/btn-loader.svg";
import estadoAlert from "../assets/figma/estado-alert.svg";
import logo from "../assets/figma/logo-giga.png";

const EASE = [0.22, 1, 0.36, 1] as const;

export default function Login() {
  const { data: cfg } = useAuthConfig();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("Regulatorio · Analista");
  const [error, setError] = useState<string | null>(params.get("error"));
  const [sending, setSending] = useState(false);
  const loggedOut = params.get("salir") === "1";
  const next = params.get("next") || "/";
  const sso = cfg?.mode === "erpnext" && cfg.oauth_ready;
  // Al volver de ERPNext se abre la página que el usuario había pedido.
  const ssoUrl = `/api/auth/login${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`;

  // SSO silencioso: si ya hay sesión en ERPNext, vuelve autenticado sin pedir credenciales.
  // No se hace tras "Cerrar sesión" (?salir=1) ni si ERPNext devolvió un error, para no entrar en bucle.
  useEffect(() => {
    if (sso && !loggedOut && !params.get("error")) window.location.assign(ssoUrl);
  }, [sso, loggedOut, params, ssoUrl]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    setError(null);
    try {
      const user = await api<User>("/api/auth/debug-login", {
        method: "POST",
        body: JSON.stringify({ email, name, role_label: role }),
      });
      qc.setQueryData(["me"], user);
      navigate(next, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "No fue posible iniciar sesión.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="login">
      <motion.div className="login__card" initial={{ opacity: 0, y: 14, scale: 0.99 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.32, ease: EASE }}>
        <div className="login__brand">
          <img src={logo} alt="GIGA+ Fibra" width={88} height={28} />
          <span className="header__divider" aria-hidden />
          <span className="header__title">Portal de reportes</span>
          {cfg && <span className="header__env">{cfg.env_label}</span>}
        </div>
        <div className="login__body">
          <h1 className="login__title">Inicia sesión</h1>
          <p className="login__text">
            Usa tu cuenta corporativa de Gigafibra. Es el mismo acceso de ERPNext con Office 365: si ya iniciaste sesión
            en ERPNext, entras directamente.
          </p>

          <AnimatePresence>
            {error && (
              <motion.p className="login__error" role="alert" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}>
                <img src={estadoAlert} alt="" width={13} height={13} /> {error}
              </motion.p>
            )}
          </AnimatePresence>

          {cfg?.mode === "erpnext" ? (
            <>
              <a className="btn btn--primary btn--full btn--lg" href={cfg.oauth_ready ? ssoUrl : undefined}
                aria-disabled={!cfg.oauth_ready}>
                <span className="btn__inner">
                  {sso && !loggedOut && !error ? <img src={btnLoader} alt="" width={16} height={16} className="spin" /> : null}
                  {sso && !loggedOut && !error ? "Conectando con ERPNext…" : "Continuar con ERPNext · Office 365"}
                </span>
              </a>
              {!cfg.oauth_ready && (
                <p className="login__hint">
                  El inicio de sesión con ERPNext aún no está configurado: falta OAUTH_CLIENT_ID en backend/.env (ver README).
                </p>
              )}
            </>
          ) : (
            <form className="login__form" onSubmit={submit}>
              <span className="login__debug">MODO DEBUG LOCAL</span>
              <label className="field">
                <span className="field__label">Correo corporativo</span>
                <input className="field__input" type="email" required autoComplete="email" value={email}
                  onChange={(e) => setEmail(e.target.value)} placeholder="nombre@gigafibra.co" />
              </label>
              <label className="field">
                <span className="field__label">Nombre</span>
                <input className="field__input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Nombre y apellido" />
              </label>
              <label className="field">
                <span className="field__label">Área · cargo</span>
                <input className="field__input" value={role} onChange={(e) => setRole(e.target.value)} />
              </label>
              <button type="submit" className="btn btn--primary btn--full btn--lg" disabled={sending}>
                <span className="btn__inner">
                  {sending && <img src={btnLoader} alt="" width={16} height={16} className="spin" />}
                  {sending ? "Ingresando…" : "Entrar al portal"}
                </span>
              </button>
              <p className="login__hint">
                Solo para desarrollo. En producción se usa el inicio de sesión de ERPNext (AUTH_MODE=erpnext).
              </p>
            </form>
          )}
        </div>
      </motion.div>
    </div>
  );
}
