import { AnimatePresence, motion } from "framer-motion";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import toastCheck from "../assets/figma/toast-check.svg";
import toastX from "../assets/figma/toast-x.svg";
import errAlert from "../assets/figma/estado-alert.svg";

type Kind = "success" | "error";
interface ToastItem {
  id: number;
  title: string;
  detail?: string;
  kind: Kind;
}

interface ToastApi {
  show: (title: string, detail?: string, kind?: Kind) => void;
}

const ToastContext = createContext<ToastApi>({ show: () => undefined });
export const useToast = () => useContext(ToastContext);

const DURATION = 4000;

function ToastCard({ item, onClose }: { item: ToastItem; onClose: () => void }) {
  const timer = useRef<number>();
  useEffect(() => {
    timer.current = window.setTimeout(onClose, DURATION);
    return () => window.clearTimeout(timer.current);
  }, [onClose]);
  return (
    <motion.div
      layout
      role="status"
      className="toast"
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 8, scale: 0.98, transition: { duration: 0.15 } }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
    >
      <span className={`toast__ic ${item.kind === "error" ? "toast__ic--error" : ""}`}>
        <img src={item.kind === "error" ? errAlert : toastCheck} alt="" width={14} height={14} />
      </span>
      <span className="toast__text">
        <span className="toast__title">{item.title}</span>
        {item.detail && <span className="toast__detail">{item.detail}</span>}
      </span>
      <button type="button" className="toast__close" aria-label="Cerrar notificación" onClick={onClose}>
        <img src={toastX} alt="" width={16} height={16} />
      </button>
    </motion.div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const remove = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const show = useCallback((title: string, detail?: string, kind: Kind = "success") => {
    const id = nextId.current++;
    setItems((xs) => [...xs.slice(-2), { id, title, detail, kind }]);
  }, []);
  const value = useMemo(() => ({ show }), [show]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" aria-live="polite">
        <AnimatePresence initial={false}>
          {items.map((t) => (
            <ToastCard key={t.id} item={t} onClose={() => remove(t.id)} />
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}
