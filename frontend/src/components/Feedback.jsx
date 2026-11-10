import { useEffect, useState } from "react";
import { AlertCircle, LoaderCircle } from "lucide-react";

export function AnimatedMetric({ value }) {
  const target = typeof value === "number" && Number.isFinite(value) ? value : null;
  const [count, setCount] = useState(target ?? 0);

  useEffect(() => {
    if (target === null) return undefined;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setCount(target);
      return undefined;
    }

    const startedAt = performance.now();
    const duration = 650;
    let frameId;
    function update(now) {
      const progress = Math.min(1, (now - startedAt) / duration);
      const eased = 1 - (1 - progress) ** 3;
      setCount(Math.round(target * eased));
      if (progress < 1) frameId = window.requestAnimationFrame(update);
    }
    frameId = window.requestAnimationFrame(update);
    return () => window.cancelAnimationFrame(frameId);
  }, [target]);

  if (target === null) return value ?? "—";
  return new Intl.NumberFormat().format(count);
}

export function LoadingState({ label = "Loading…" }) {
  return (
    <div className="loading-state" role="status">
      <LoaderCircle className="spin" size={20} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorMessage({ children, onRetry }) {
  if (!children) return null;
  return (
    <div className="error-banner" role="alert">
      <AlertCircle size={18} />
      <span>{children}</span>
      {onRetry && (
        <button type="button" className="button button-quiet" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}

export function PageHeading({ eyebrow, title, description, actions }) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function StatusBadge({ children }) {
  const status = String(children ?? "unknown").toLowerCase().replaceAll(" ", "_");
  return <span className={`status-badge status-${status}`}>{children}</span>;
}
