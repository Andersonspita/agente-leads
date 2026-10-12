import { AlertCircle, CheckCircle2, Circle, Loader2, MinusCircle, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import type { Artifact, Box, CompareRow, DimensionScore, Finding, LeadStatus, Severidade, Step } from "@/api/types";
import { Badge } from "@/components/ui";
import { DIMENSIONS, LEAD_STATUS, SEVERITIES, STEP_STATUS } from "@/lib/labels";
import { band, bandBg, bandStroke, bandText, cn } from "@/lib/utils";

/** Nota 0–100 com cor e rótulo (nunca só cor). */
export function ScoreGauge({ score, size = 132, label }: { score: number | null | undefined; size?: number; label?: string }) {
  const b = band(score);
  const r = 42;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - (score ?? 0) / 100);
  return (
    <div className="flex flex-col items-center gap-1" role="img" aria-label={`${label ?? "Nota"}: ${score ?? "não medida"} de 100, ${b.rotulo}`}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg viewBox="0 0 100 100" className="-rotate-90" width={size} height={size} aria-hidden>
          <circle cx="50" cy="50" r={r} fill="none" stroke="var(--border)" strokeWidth="9" />
          <circle
            cx="50"
            cy="50"
            r={r}
            fill="none"
            stroke={bandStroke[b.faixa]}
            strokeWidth="9"
            strokeLinecap="round"
            strokeDasharray={circ}
            strokeDashoffset={offset}
            style={{ transition: "stroke-dashoffset .6s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn("font-bold tabular-nums", bandText[b.faixa])} style={{ fontSize: size * 0.3 }}>
            {score ?? "—"}
          </span>
          <span className="text-[11px] text-muted">de 100</span>
        </div>
      </div>
      <Badge className={bandBg[b.faixa]}>{b.rotulo}</Badge>
    </div>
  );
}

export function ScoreChip({ score }: { score: number | null | undefined }) {
  const b = band(score);
  if (score === null || score === undefined) return <span className="text-muted">—</span>;
  return (
    <Badge className={cn(bandBg[b.faixa], "tabular-nums")}>
      {score} <span className="sr-only">({b.rotulo})</span>
    </Badge>
  );
}

/** Nota por dimensão + nº de achados. */
export function DimensionCard({ dim, onClick, active }: { dim: DimensionScore; onClick?: () => void; active?: boolean }) {
  const meta = DIMENSIONS[dim.chave];
  const Icon = meta.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col gap-2 rounded-lg border bg-surface p-3 text-left transition-colors hover:border-brand/60",
        active ? "border-brand ring-2 ring-brand/20" : "border-border",
      )}
      aria-pressed={active}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-2">
        <span className="flex items-center gap-1.5 text-xs font-medium text-muted">
          <Icon className="size-3.5" strokeWidth={1.75} aria-hidden /> {meta.nome}
        </span>
        {dim.peso !== null && dim.peso !== undefined && <span className="whitespace-nowrap text-[10px] text-muted">peso {Math.round(dim.peso * 100)}%</span>}
      </div>
      <div className="flex flex-wrap items-end justify-between gap-x-2">
        <span className={cn("text-2xl font-bold tabular-nums", bandText[dim.faixa])}>{dim.nota ?? "—"}</span>
        <span className="whitespace-nowrap text-xs text-muted">
          {dim.achados} {dim.achados === 1 ? "achado" : "achados"}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-2" aria-hidden>
        <div className="h-full rounded-full" style={{ width: `${dim.nota ?? 0}%`, background: bandStroke[dim.faixa] }} />
      </div>
      <span className={cn("self-start rounded px-1.5 text-[11px] font-medium", bandBg[dim.faixa])}>{dim.rotulo}</span>
    </button>
  );
}

export function SeverityBadge({ severity }: { severity: Severidade }) {
  const s = SEVERITIES[severity];
  return <Badge className={s.className}>{s.nome}</Badge>;
}

export function StatusPill({ status }: { status: LeadStatus }) {
  const s = LEAD_STATUS[status];
  return <Badge className={s.className}>{s.nome}</Badge>;
}

export function OriginBadge({ origin }: { origin: Finding["origem"] }) {
  if (origin === "ia")
    return (
      <Badge className="border border-dashed border-violet-400 text-violet-700 dark:text-violet-300">
        <Sparkles className="size-3" aria-hidden /> Avaliação assistida
      </Badge>
    );
  if (origin === "manual") return <Badge className="bg-surface-2 text-muted">Analista</Badge>;
  return <Badge className="bg-surface-2 text-muted">Regra automática</Badge>;
}

/** Título, severidade, impacto, evidência e ações de revisão. */
export function FindingItem({ finding, actions, selected, onSelect }: { finding: Finding; actions?: ReactNode; selected?: boolean; onSelect?: () => void }) {
  const Icon = DIMENSIONS[finding.dimensao].icon;
  return (
    <div
      onClick={onSelect}
      className={cn(
        "rounded-md border px-3 py-2.5 transition-colors",
        onSelect && "cursor-pointer",
        selected ? "border-brand bg-brand/5" : "border-border bg-surface hover:bg-surface-2",
        finding.status_revisao === "descartado" && "opacity-55",
      )}
    >
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 size-4 shrink-0 text-muted" strokeWidth={1.75} aria-label={finding.dimensao_nome} />
        <div className="min-w-0 flex-1">
          <p className={cn("font-medium leading-snug", finding.status_revisao === "descartado" && "line-through")}>{finding.titulo}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <SeverityBadge severity={finding.severidade} />
            <OriginBadge origin={finding.origem} />
            {finding.rule_id && <span className="font-mono text-[11px] text-muted">{finding.rule_id}</span>}
            <ReviewBadge status={finding.status_revisao} />
          </div>
          {finding.impacto_negocio && <p className="mt-1.5 line-clamp-2 text-xs text-muted">{finding.impacto_negocio}</p>}
        </div>
        {actions}
      </div>
    </div>
  );
}

export function ReviewBadge({ status }: { status: Finding["status_revisao"] }) {
  if (status === "confirmado") return <Badge className="bg-good-soft text-good">Confirmado</Badge>;
  if (status === "descartado") return <Badge className="bg-surface-2 text-muted">Descartado</Badge>;
  return <Badge className="bg-weak-soft text-weak">Pendente</Badge>;
}

/** Captura com caixas numeradas sobre os problemas. */
export function ScreenshotAnnotated({ artifact, boxes = [], alt, maxHeight = 520 }: { artifact?: Artifact; boxes?: Box[]; alt: string; maxHeight?: number }) {
  if (!artifact) {
    return <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-border text-xs text-muted">Captura indisponível</div>;
  }
  const w = artifact.meta.largura ?? 1440;
  const h = artifact.meta.altura ?? 900;
  return (
    <div className="overflow-auto rounded-md border border-border bg-surface-2" style={{ maxHeight }}>
      <div className="relative">
        <img src={artifact.url} alt={alt} className="block w-full" loading="lazy" />
        {boxes
          .filter((b) => b.y < h)
          .map((b, i) => (
            <div
              key={i}
              className="absolute rounded border-[3px] border-rose-600"
              style={{ left: `${(b.x / w) * 100}%`, top: `${(b.y / h) * 100}%`, width: `${Math.max((b.w / w) * 100, 1.5)}%`, height: `${Math.max((b.h / h) * 100, 0.5)}%` }}
            >
              <span className="absolute -left-2.5 -top-2.5 flex size-5 items-center justify-center rounded-full bg-rose-600 text-[10px] font-bold text-white">{i + 1}</span>
            </div>
          ))}
      </div>
    </div>
  );
}

/** Barras comparativas com destaque do lead. */
export function CompetitorBar({ rows, reference }: { rows: CompareRow[]; reference: number }) {
  return (
    <ul className="space-y-2">
      {rows.map((r, i) => {
        const b = band(r.nota);
        return (
          <li key={`${r.nome}-${i}`} className="grid grid-cols-[minmax(0,12rem)_1fr_3rem] items-center gap-3 text-sm">
            <span className={cn("truncate", r.destaque && "font-semibold")} title={r.nome}>
              {r.nome}
              {r.destaque && " (lead)"}
            </span>
            <span className="relative h-5 rounded bg-surface-2" role="img" aria-label={`${r.nome}: ${r.nota ?? "sem nota"} de 100`}>
              <span className="block h-full rounded" style={{ width: `${r.nota ?? 0}%`, background: r.destaque ? "var(--color-brand)" : bandStroke[b.faixa], opacity: r.destaque ? 1 : 0.55 }} />
              <span className="absolute -bottom-1 -top-1 border-l-2 border-dashed border-fg/70" style={{ left: `${reference}%` }} title={`Referência ${reference}`} />
            </span>
            <span className={cn("text-right font-semibold tabular-nums", bandText[b.faixa])}>{r.nota ?? "—"}</span>
          </li>
        );
      })}
    </ul>
  );
}

const STEP_ICON: Record<Step["status"], ReactNode> = {
  pendente: <Circle className="size-4 text-muted" aria-hidden />,
  executando: <Loader2 className="size-4 animate-spin text-brand" aria-hidden />,
  ok: <CheckCircle2 className="size-4 text-good" aria-hidden />,
  falhou: <AlertCircle className="size-4 text-bad" aria-hidden />,
  nao_medido: <MinusCircle className="size-4 text-muted" aria-hidden />,
};

/** Progresso das etapas da auditoria. */
export function JobProgress({ steps, compact }: { steps: Step[]; compact?: boolean }) {
  const done = steps.filter((s) => !["pendente", "executando"].includes(s.status)).length;
  return (
    <div>
      <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={done}>
        <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${(done / Math.max(steps.length, 1)) * 100}%` }} />
      </div>
      <ol className={cn("grid gap-1.5", compact ? "grid-cols-3 sm:grid-cols-9" : "sm:grid-cols-3")}>
        {steps.map((s) => (
          <li key={s.etapa} className="flex items-start gap-2 text-xs" title={s.erro || STEP_STATUS[s.status]}>
            {STEP_ICON[s.status]}
            {!compact && (
              <div className="min-w-0">
                <p className="font-medium">
                  {s.ordem}. {s.nome}
                </p>
                <p className="truncate text-muted">
                  {STEP_STATUS[s.status]}
                  {s.duracao_ms ? ` · ${(s.duracao_ms / 1000).toFixed(1)} s` : ""}
                  {s.erro ? ` — ${s.erro}` : ""}
                </p>
              </div>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

export function SiteStateIcon({ state }: { state: "sem_site" | "fora_do_ar" | "tem_site" }) {
  const map = {
    tem_site: { cls: "bg-good", label: "Tem site" },
    fora_do_ar: { cls: "bg-bad", label: "Site fora do ar" },
    sem_site: { cls: "bg-weak", label: "Sem site" },
  }[state];
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className={cn("size-2 rounded-full", map.cls)} aria-hidden />
      {map.label}
    </span>
  );
}
