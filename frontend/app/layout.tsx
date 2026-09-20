import type { Metadata } from 'next';
import './globals.css';
import { DisclaimerBanner } from '@/components/DisclaimerBanner';
import { ConfigProvider } from '@/context/ConfigContext';

export const metadata: Metadata = {
  title: 'NyayaSetu - Multi-Agent Legal Assistance',
  description:
    'Citizen-facing legal assistance grounded in statutory text with multi-agent verification, debate, and citation auditing.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 antialiased">
      <body className="min-h-full flex flex-col font-sans">
        {/* Persistent Legal Disclaimer visible on every screen, not dismissible */}
        <DisclaimerBanner />

        {/* Global Brand Header */}
        <header className="border-b border-slate-200/80 bg-white/80 backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/80">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3 sm:px-6">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-700 to-indigo-500 text-white shadow-md shadow-indigo-600/20 font-bold text-sm">
                ⚖️
              </div>
              <div>
                <h1 className="text-base font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
                  NyayaSetu
                  <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                    Multi-Agent AI
                  </span>
                </h1>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Statutory Grounding & Adversarial Legal Analysis
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div className="hidden sm:flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
                Citation Audited
              </div>
            </div>
          </div>
        </header>

        {/* Client Config Provider wrapping main content */}
        <ConfigProvider>
          <main className="flex-1 flex flex-col">{children}</main>
        </ConfigProvider>
      </body>
    </html>
  );
}
