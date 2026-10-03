// frontend/src/components/brand/Logo.tsx
// الرمز يقرأ ألوانه من tokens.css فيتبدّل تلقائيًا مع data-theme.
// الشعار الأفقي (مع الاسم) صور SVG ثابتة المسارات من frontend/public/brand/.
import type { CSSProperties, SVGProps } from "react";

type MarkProps = SVGProps<SVGSVGElement> & { size?: number; halo?: boolean };

/** الرمز وحده: للسايدبار، التبويب، أزرار صغيرة. تحت 28px تُستخدم نسخة أسمك تلقائيًا. */
export function RootIQMark({ size = 32, halo, ...rest }: MarkProps) {
  const heavy = size <= 28;
  const sw = heavy ? 6.5 : 5;
  const x0 = heavy ? 16.5 : 16;
  const showHalo = halo ?? size >= 32;
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="RootIQ" {...rest}>
      <g fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path d="M29 34L44 49" stroke="var(--brand)" strokeWidth={sw} />
        <path
          d={`M${x0} 9V53M${x0} 9H31A12.5 12.5 0 0 1 31 34H${x0}`}
          stroke="var(--text-1)"
          strokeWidth={sw}
        />
      </g>
      {showHalo && (
        <circle cx="47" cy="52" r="10.5" fill="none" stroke="var(--brand)" strokeWidth={2} opacity={0.45} />
      )}
      <circle cx="47" cy="52" r={heavy ? 6.5 : 6} fill="var(--brand)" />
    </svg>
  );
}

/** الشعار الأفقي (الرمز + الاسم). lang يحدد النسخة العربية أو الإنجليزية. */
export function RootIQLogo({ lang = "en", height = 28 }: { lang?: "ar" | "en"; height?: number }) {
  const base = lang === "ar" ? "/brand/rootiq-logo-ar" : "/brand/rootiq-logo";
  const style = { "--logo-h": `${height}px` } as CSSProperties;
  return (
    <>
      <img className="rq-logo rq-logo--dark" src={`${base}.svg`} alt="RootIQ" style={style} />
      <img className="rq-logo rq-logo--light" src={`${base}-on-light.svg`} alt="" aria-hidden="true" style={style} />
    </>
  );
}
