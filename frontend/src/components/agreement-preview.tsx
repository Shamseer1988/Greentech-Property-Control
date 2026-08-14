"use client";

export type Clause = {
  heading_en: string | null;
  heading_ar: string | null;
  body_en: string;
  body_ar: string;
};

/**
 * The bilingual two-column layout (English left / Arabic right) that
 * mirrors the generated .docx exactly — both are built from the same
 * clause list returned by the backend, so what's shown here is what
 * gets downloaded.
 */
export function AgreementPreview({ clauses }: { clauses: Clause[] }) {
  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <table className="w-full text-sm border-collapse">
        <tbody className="divide-y divide-border">
          {clauses.map((c, i) => (
            <tr key={i} className="align-top">
              <td className="w-1/2 p-3 border-r border-border">
                {c.heading_en && <div className="font-semibold text-xs mb-1">{c.heading_en}</div>}
                {c.body_en.split("\n\n").map((p, j) => (
                  <p key={j} className="text-xs leading-relaxed mb-1.5 last:mb-0">{p}</p>
                ))}
              </td>
              <td className="w-1/2 p-3" dir="rtl">
                {c.heading_ar && <div className="font-semibold text-xs mb-1">{c.heading_ar}</div>}
                {c.body_ar.split("\n\n").map((p, j) => (
                  <p key={j} className="text-xs leading-relaxed mb-1.5 last:mb-0">{p}</p>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
