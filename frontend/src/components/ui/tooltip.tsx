"use client";

import * as React from "react";
import * as RadixTooltip from "@radix-ui/react-tooltip";

/**
 * Thin wrapper around Radix Tooltip so feature components don't have to
 * wire up Provider + Root + Trigger + Content every time.
 *
 * Use for short, hover-only info — for action menus reach for a Modal or
 * Popover. The content is positioned above the trigger by default.
 */
export function Tooltip({
  children,
  content,
  side = "top",
  align = "center",
  delayDuration = 150,
  className,
}: {
  children: React.ReactNode;
  content: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  delayDuration?: number;
  className?: string;
}) {
  return (
    <RadixTooltip.Provider delayDuration={delayDuration}>
      <RadixTooltip.Root>
        <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
        <RadixTooltip.Portal>
          <RadixTooltip.Content
            side={side}
            align={align}
            sideOffset={8}
            collisionPadding={12}
            className={
              // Solid card background — Tailwind config has no `popover`
              // token, so the old `bg-popover` resolved to nothing and
              // the tooltip rendered transparent / unreadable. Use the
              // card token (opaque) and bump padding + text to make
              // unit/contract details legible at hover.
              "z-50 max-w-sm rounded-lg border border-border bg-card text-card-foreground " +
              "shadow-xl px-3.5 py-2.5 text-sm leading-snug " +
              "data-[state=delayed-open]:animate-in data-[state=closed]:animate-out " +
              "data-[state=closed]:fade-out-0 data-[state=delayed-open]:fade-in-0 " +
              (className ?? "")
            }
          >
            {content}
            <RadixTooltip.Arrow className="fill-card" />
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
