import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError, downloadVersion } from "../api/client";
import { useMe } from "../api/hooks";
import type { ReportKey, Version } from "../api/types";
import { useToast } from "../components/Toast";

/**
 * Acciones de descarga y generación. El estado "Preparando…" vive aquí (no en la fila),
 * así se conserva al cambiar de página y no bloquea la tabla ni la navegación.
 */
interface Actions {
  /** El usuario tiene el rol de ERPNext para generar (System Manager); si no, solo consulta y descarga. */
  canGenerate: boolean;
  deniedReason: string;
  isBusy: (key: string) => boolean;
  download: (v: Version) => Promise<void>;
  generate: (report: ReportKey, period: string, opts?: { downloadWhenReady?: boolean }) => Promise<void>;
}

const ActionsContext = createContext<Actions | null>(null);

export const periodKey = (report: string, period: string) => `p:${report}:${period}`;
export const versionKey = (id: number) => `v:${id}`;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function ActionsProvider({ children }: { children: ReactNode }) {
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const toast = useToast();
  const qc = useQueryClient();
  const me = useMe().data;
  const canGenerate = me?.can_generate ?? false;
  const deniedReason =
    me?.generate_denied_reason ??
    `Solo los usuarios con el rol ${(me?.generate_roles ?? ["System Manager"]).join(" o ")} en ERPNext pueden generar reportes.`;

  const mark = useCallback((key: string, on: boolean) => {
    setBusy((prev) => {
      const next = new Set(prev);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);

  const refresh = useCallback(() => {
    qc.invalidateQueries({ queryKey: ["dashboard"] });
    qc.invalidateQueries({ queryKey: ["report"] });
    qc.invalidateQueries({ queryKey: ["periods"] });
    qc.invalidateQueries({ queryKey: ["history"] });
    qc.invalidateQueries({ queryKey: ["meta"] });
  }, [qc]);

  const download = useCallback(
    async (v: Version) => {
      const key = versionKey(v.id);
      if (busyRef.current.has(key)) return;
      mark(key, true);
      try {
        await downloadVersion(v.id, (filename) => toast.show("Descarga iniciada", filename));
      } catch (e) {
        toast.show("No se pudo descargar", e instanceof Error ? e.message : undefined, "error");
      } finally {
        mark(key, false);
      }
    },
    [mark, toast],
  );

  const generate = useCallback(
    async (report: ReportKey, period: string, opts?: { downloadWhenReady?: boolean }) => {
      const key = periodKey(report, period);
      if (busyRef.current.has(key)) return;
      mark(key, true);
      try {
        let v = await api<Version>(`/api/reports/${report}/periods/${period}/generate`, { method: "POST" });
        refresh();
        for (let i = 0; i < 400 && v.status === "processing"; i++) {
          await sleep(i < 5 ? 1200 : 2500);
          v = await api<Version>(`/api/versions/${v.id}`);
        }
        refresh();
        if (v.status === "available") {
          if (opts?.downloadWhenReady) {
            await downloadVersion(v.id, (filename) => toast.show("Descarga iniciada", filename));
          } else {
            toast.show("Archivo generado", v.filename ?? undefined);
          }
        }
        // Si quedó en error, la fila muestra el mensaje y la acción "Reintentar".
      } catch (e) {
        toast.show("No se pudo generar el archivo", e instanceof Error ? e.message : undefined, "error");
        // Un 403 indica que el rol cambió en ERPNext: se refresca el usuario para ocultar las acciones.
        if (e instanceof ApiError && e.status === 403) qc.invalidateQueries({ queryKey: ["me"] });
        refresh();
      } finally {
        mark(key, false);
      }
    },
    [mark, refresh, toast],
  );

  const value = useMemo<Actions>(
    () => ({ canGenerate, deniedReason, isBusy: (k) => busy.has(k), download, generate }),
    [canGenerate, deniedReason, busy, download, generate],
  );
  return <ActionsContext.Provider value={value}>{children}</ActionsContext.Provider>;
}

export function useActions(): Actions {
  const ctx = useContext(ActionsContext);
  if (!ctx) throw new Error("ActionsProvider no encontrado");
  return ctx;
}
