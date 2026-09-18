import { ArrowUpRight, DatabaseZap } from "lucide-react";
import PageIntro from "./PageIntro.jsx";

export default function PlaceholderPage({ eyebrow, title, description, icon: Icon, emptyTitle, emptyDescription, plannedItems }) {
  return (
    <>
      <PageIntro eyebrow={eyebrow} title={title} description={description} />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <section className="overflow-hidden rounded-2xl border border-[#e4ebe3] bg-white shadow-[0_2px_14px_rgba(27,58,39,0.035)]">
          <div className="flex items-center justify-between border-b border-[#edf1ec] px-5 py-4 sm:px-6">
            <h2 className="text-sm font-semibold text-[#2b4834]">{title} workspace</h2>
            <span className="rounded-full bg-[#f1f5ef] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[#798e7b]">Awaiting data</span>
          </div>
          <div className="spatial-grid flex min-h-[430px] flex-col items-center justify-center px-6 py-12 text-center sm:min-h-[520px]">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-[#dce9dd] bg-white text-[#4e875f] shadow-sm">
              <Icon size={28} strokeWidth={1.5} aria-hidden="true" />
            </div>
            <h3 className="mt-6 text-lg font-semibold text-[#294532]">{emptyTitle}</h3>
            <p className="mt-2 max-w-md text-sm leading-6 text-[#7b8c7e]">{emptyDescription}</p>
          </div>
        </section>

        <aside className="space-y-5">
          <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 shadow-[0_2px_14px_rgba(27,58,39,0.035)]">
            <div className="flex items-center gap-2 text-[#3c7350]">
              <DatabaseZap size={18} strokeWidth={1.8} aria-hidden="true" />
              <h2 className="text-sm font-semibold text-[#294532]">Connection status</h2>
            </div>
            <p className="mt-3 text-xs leading-5 text-[#7a8a7e]">This page is ready for a verified data connection. No measurements or model results are shown yet.</p>
            <div className="mt-5 flex items-center gap-2 border-t border-[#edf1ec] pt-4 text-xs font-medium text-[#9a8051]">
              <span className="h-2 w-2 rounded-full bg-[#cfb477]" />
              Source not connected
            </div>
          </section>
          <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 shadow-[0_2px_14px_rgba(27,58,39,0.035)]">
            <h2 className="text-sm font-semibold text-[#294532]">Planned for this view</h2>
            <ul className="mt-4 space-y-3">
              {plannedItems.map((item) => (
                <li key={item} className="flex items-start gap-2.5 text-xs leading-5 text-[#718276]">
                  <ArrowUpRight size={15} className="mt-0.5 shrink-0 text-[#5b9270]" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </>
  );
}
