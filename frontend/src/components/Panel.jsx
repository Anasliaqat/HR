export default function Panel({
  title,
  subtitle,
  action,
  children,
  className = "",
  id,
}) {
  return (
    <section className={`panel ${className}`} id={id}>
      {(title || action) && (
        <div className="panel-heading">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
