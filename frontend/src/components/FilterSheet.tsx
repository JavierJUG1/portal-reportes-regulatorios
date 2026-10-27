import { AnimatePresence, motion } from "framer-motion";
import type { ReactNode } from "react";
import drawerX from "../assets/figma/icon-x-drawer.svg";

/** Hoja inferior para los filtros en móvil (botón "Filtros"). */
export function FilterSheet({ open, onClose, children, onClear }: {
  open: boolean;
  onClose: () => void;
  onClear: () => void;
  children: ReactNode;
}) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="overlay" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.2 }} />
          <motion.div
            className="sheet"
            role="dialog"
            aria-modal="true"
            aria-label="Filtros"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="sheet__grip" aria-hidden />
            <div className="sheet__head">
              <span className="sheet__title">Filtros</span>
              <button type="button" className="drawer__close" onClick={onClose} aria-label="Cerrar filtros">
                <img src={drawerX} alt="" width={20} height={20} />
              </button>
            </div>
            <div className="sheet__body">{children}</div>
            <div className="sheet__foot">
              <button type="button" className="link-btn" onClick={onClear}>Limpiar todo</button>
              <button type="button" className="btn btn--dark" onClick={onClose}>
                <span className="btn__inner">Ver resultados</span>
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
