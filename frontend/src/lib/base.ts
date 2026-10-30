/**
 * Ruta base donde está publicado el portal: "/" en la raíz, o p. ej. "/portal_reportes_crc/" detrás de nginx.
 * La define el backend (BASE_PATH) con <base href> en index.html; en `npm run dev` no hay <base> y es "/".
 */
export const BASE_PATH = (() => {
  const href = document.querySelector("base")?.getAttribute("href") || "/";
  return href.endsWith("/") ? href : `${href}/`;
})();

/** Base para React Router ("/" o "/portal_reportes_crc"). */
export const ROUTER_BASENAME = BASE_PATH.length > 1 ? BASE_PATH.slice(0, -1) : "/";

/** Ruta absoluta del portal ("/api/meta") → URL bajo la ruta base ("/portal_reportes_crc/api/meta"). */
export function withBase(path: string): string {
  return BASE_PATH + path.replace(/^\//, "");
}
