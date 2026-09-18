export default function PageIntro({ eyebrow, title, description }) {
  return (
    <div className="mb-7">
      <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.18em] text-[#42815a]">{eyebrow}</p>
      <h1 className="text-2xl font-bold tracking-tight text-[#1c3a29] sm:text-[30px]">{title}</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-[#718176]">{description}</p>
    </div>
  );
}
