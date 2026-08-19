import React, { createContext, useContext, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, CheckCircle, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastType = "success" | "error";

interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({ showToast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  let counter = 0;

  const showToast = useCallback((message: string, type: ToastType = "success") => {
    const id = ++counter;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  const remove = (id: number) => setToasts((prev) => prev.filter((t) => t.id !== id));

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
        <AnimatePresence>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 12 }}
              transition={{ duration: 0.25 }}
              className={cn(
                "flex items-center gap-g2 px-g4 py-g3 rounded-lg shadow-card-hover text-base font-semibold min-w-72 border bg-white",
                toast.type === "success"
                  ? "text-machine-healthy border-machine-healthy/25"
                  : "text-destructive border-destructive/25"
              )}
            >
              {toast.type === "success" ? <CheckCircle size={18} /> : <AlertCircle size={18} />}
              <span className="flex-1 text-foreground font-medium">{toast.message}</span>
              <button onClick={() => remove(toast.id)} className="p-1 rounded hover:bg-muted transition-colors">
                <X size={14} className="text-muted-foreground" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}
