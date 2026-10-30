import { withBase } from "../lib/base";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let message = "Hubo un problema al consultar el servidor.";
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") message = data.detail;
  } catch {
    /* respuesta sin JSON */
  }
  return new ApiError(res.status, message);
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(withBase(path), {
    credentials: "include",
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
    ...init,
  });
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    window.dispatchEvent(new CustomEvent("portal:unauthorized"));
  }
  if (!res.ok) throw await parseError(res);
  return res.json() as Promise<T>;
}

export function qs(params: Record<string, string | number | null | undefined>): string {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== "") sp.set(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
}

/** Descarga el archivo; resuelve cuando el backend confirma el inicio (cabeceras recibidas). */
export async function downloadVersion(id: number, onStarted: (filename: string) => void): Promise<void> {
  const res = await fetch(withBase(`/api/versions/${id}/download`), { credentials: "include" });
  if (!res.ok) throw await parseError(res);
  const encoded = res.headers.get("X-Filename");
  const filename = encoded ? decodeURIComponent(encoded) : `reporte_${id}.xlsx`;
  onStarted(filename);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
