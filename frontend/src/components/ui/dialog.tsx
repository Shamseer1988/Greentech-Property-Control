"use client";

import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X, type LucideIcon } from "lucide-react";

export function Modal({
  open,
  onClose,
  title,
  description,
  icon: Icon,
  children,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  /** One line under the title — what this dialog is for, or the record
   * it acts on. Optional; most confirm-style dialogs don't need one. */
  description?: string;
  /** A small icon badge beside the title. Optional. */
  icon?: LucideIcon;
  children: React.ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const sizes = { sm: "max-w-md", md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl" };
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 grid place-items-center bg-black/50 backdrop-blur-sm p-4"
          role="dialog" aria-modal="true" aria-label={title}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 6 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className={`glass-strong w-full ${sizes[size]} rounded-2xl p-6 relative max-h-[90vh] overflow-y-auto`}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              aria-label="Close dialog"
              onClick={onClose}
              className="absolute top-4 right-4 h-8 w-8 rounded-full text-muted-foreground hover:bg-accent hover:text-foreground grid place-items-center transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
            <div className="flex items-start gap-3 pr-8 mb-4">
              {Icon && (
                <div className="h-10 w-10 shrink-0 rounded-xl bg-gradient-to-br from-primary/15 to-primary/5 border border-primary/10 grid place-items-center">
                  <Icon className="h-5 w-5 text-primary" />
                </div>
              )}
              <div className="min-w-0 pt-0.5">
                <h2 className="text-lg font-semibold leading-tight tracking-tight">{title}</h2>
                {description && (
                  <p className="mt-1 text-sm text-muted-foreground">{description}</p>
                )}
              </div>
            </div>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Field({ label, children, span = 1 }: { label: string; children: React.ReactNode; span?: 1 | 2 }) {
  return (
    <div className={`space-y-1 ${span === 2 ? "col-span-2" : ""}`}>
      <label className="text-sm font-medium">{label}</label>
      {children}
    </div>
  );
}

export const inputClass =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm " +
  "placeholder:text-muted-foreground/70 transition-colors " +
  "hover:border-ring/50 " +
  "focus:outline-none focus:ring-2 focus:ring-ring focus:border-ring " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

export const textareaClass =
  "w-full min-h-[80px] rounded-md border border-input bg-background p-3 text-sm " +
  "placeholder:text-muted-foreground/70 " +
  "focus:outline-none focus:ring-2 focus:ring-ring focus:border-ring " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

export const selectClass = inputClass;
