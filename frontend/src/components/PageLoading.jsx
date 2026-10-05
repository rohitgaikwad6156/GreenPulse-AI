export default function PageLoading({ label }) {
  return (
    <section className="page-loading" role="status" aria-live="polite" aria-busy="true">
      <p className="eyebrow">Preparing your workspace</p>
      <p>{label}</p>
      <div className="loading-placeholder" aria-hidden="true" />
      <div className="loading-placeholder short" aria-hidden="true" />
    </section>
  );
}
