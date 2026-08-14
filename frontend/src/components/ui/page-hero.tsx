import type { LucideIcon } from "lucide-react";

/** The gradient hero header used at the top of top-level pages — icon
 * badge, title, one-line description, blurred decorative circle, and an
 * optional right-aligned action (e.g. a "New X" button). */
export function PageHero({ icon: Icon, title, description, action }: {
  icon: LucideIcon; title: string; description: string; action?: React.ReactNode;
}) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-br from-primary/10 via-card/60 to-card/30 p-5 sm:p-6 backdrop-blur">
      <div className="absolute -top-16 -right-16 h-48 w-48 rounded-full bg-primary/10 blur-3xl pointer-events-none" />
      <div className="relative flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="grid place-items-center h-11 w-11 rounded-xl bg-primary/10 text-primary shrink-0">
            <Icon className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight">{title}</h1>
            <p className="text-sm text-muted-foreground mt-0.5">{description}</p>
          </div>
        </div>
        {action}
      </div>
    </div>
  );
}
