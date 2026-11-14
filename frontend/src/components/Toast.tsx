import { useEffect } from "react";
import { CheckCircle2, AlertCircle, X } from "lucide-react";

export interface ToastMessage {
  id: string;
  type: "success" | "error" | "info";
  message: string;
}

interface Props {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export function Toast({ toasts, onDismiss }: Props) {
  useEffect(() => {
    if (toasts.length === 0) return;
    const latest = toasts[toasts.length - 1];
    const timer = setTimeout(() => {
      onDismiss(latest.id);
    }, 4000);
    return () => clearTimeout(timer);
  }, [toasts, onDismiss]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm pointer-events-none">
      {toasts.map((toast) => {
        const isError = toast.type === "error";
        const isSuccess = toast.type === "success";

        return (
          <div
            key={toast.id}
            role="status"
            className={`pointer-events-auto flex items-start gap-2.5 p-3 rounded-control border text-13 ${
              isError
                ? "bg-surface border-accent text-text"
                : isSuccess
                ? "bg-surface border-border text-text"
                : "bg-surface border-border text-muted"
            }`}
          >
            {isError ? (
              <AlertCircle size={16} strokeWidth={1.5} className="text-accent shrink-0 mt-0.5" />
            ) : isSuccess ? (
              <CheckCircle2 size={16} strokeWidth={1.5} className="text-ok shrink-0 mt-0.5" />
            ) : (
              <span className="w-2 h-2 rounded-full bg-muted shrink-0 mt-1.5" />
            )}

            <div className="flex-1 leading-snug">{toast.message}</div>

            <button
              type="button"
              onClick={() => onDismiss(toast.id)}
              className="text-muted hover:text-text p-0.5 -mr-1"
              aria-label="Dismiss message"
            >
              <X size={14} strokeWidth={1.5} />
            </button>
          </div>
        );
      })}
    </div>
  );
}

