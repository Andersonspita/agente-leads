import { useQuery } from "@tanstack/react-query";
import { FileBarChart, LayoutDashboard, LogOut, Moon, Radar, Search, Settings, Sun, Users } from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { api } from "@/api/client";
import type { Dashboard } from "@/api/types";
import { useAuth } from "@/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Painel", icon: LayoutDashboard, end: true },
  { to: "/buscas", label: "Buscas", icon: Search },
  { to: "/leads", label: "Leads", icon: Users },
  { to: "/auditorias", label: "Auditorias", icon: Radar },
  { to: "/relatorios", label: "Relatórios", icon: FileBarChart },
  { to: "/configuracoes", label: "Configurações", icon: Settings },
];

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const toggle = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("tema", next ? "escuro" : "claro");
    } catch {
      /* armazenamento indisponível: só não lembra a preferência */
    }
    setDark(next);
  };
  return { dark, toggle };
}

export function Layout() {
  const { me, logout } = useAuth();
  const { dark, toggle } = useTheme();
  const { data } = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("dashboard"), refetchInterval: 30_000 });
  const pending = data?.revisao_pendente ?? 0;

  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-border bg-surface max-md:w-14">
        <div className="flex h-14 items-center gap-2 border-b border-border px-4">
          <img src="/favicon.svg" alt="" className="size-6" />
          <span className="font-semibold max-md:hidden">Auditor de Sites</span>
        </div>
        <nav className="flex-1 space-y-0.5 p-2" aria-label="Principal">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              title={label}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-brand/10 text-brand dark:text-blue-300" : "text-muted hover:bg-surface-2 hover:text-fg",
                )
              }
            >
              <Icon className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />
              <span className="max-md:hidden">{label}</span>
              {to === "/auditorias" && pending > 0 && (
                <span className="ml-auto rounded-full bg-weak-soft px-1.5 text-[11px] font-semibold text-weak max-md:hidden" title="Auditorias com achados pendentes de revisão">
                  {pending}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-1 border-t border-border p-2">
          <button onClick={toggle} className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-muted hover:bg-surface-2 hover:text-fg" title="Alternar tema">
            {dark ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
            <span className="max-md:hidden">{dark ? "Tema claro" : "Tema escuro"}</span>
          </button>
          <div className="px-2.5 py-1 text-xs text-muted max-md:hidden">
            <p className="truncate font-medium text-fg">{me?.user?.nome}</p>
            <p>{me?.user?.role === "admin" ? "Administrador" : "Analista"}</p>
          </div>
          <button onClick={logout} className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-muted hover:bg-surface-2 hover:text-fg" title="Sair">
            <LogOut className="size-4" aria-hidden />
            <span className="max-md:hidden">Sair</span>
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}

/** Cabeçalho de página: título + ação primária (o próximo passo do fluxo). */
export function PageHeader({ title, description, actions, back }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; back?: ReactNode }) {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-bg/90 backdrop-blur">
      <div className="flex min-h-14 flex-wrap items-center justify-between gap-3 px-6 py-2.5">
        <div className="min-w-0">
          {back && <div className="text-xs text-muted">{back}</div>}
          <h1 className="truncate text-lg font-semibold">{title}</h1>
          {description && <p className="text-xs text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}

export function PageBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("space-y-4 p-6", className)}>{children}</div>;
}
