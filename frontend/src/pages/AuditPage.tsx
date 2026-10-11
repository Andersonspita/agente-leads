import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, ClipboardCheck, FileBarChart, Loader2, RefreshCw, Sparkles, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { AuditDetail, Dimensao, Finding } from "@/api/types";
import { PageBody, PageHeader } from "@/components/Layout";
import { DimensionCard, FindingItem, JobProgress, ScoreGauge, ScreenshotAnnotated } from "@/components/domain";
import { useToast } from "@/components/toast";
import { Badge, Button, Card, CardHeader, ErrorState, Loading, Tabs } from "@/components/ui";
import { SEVERITIES } from "@/lib/labels";
import { fmtBytes, fmtDateTime, fmtSeconds } from "@/lib/utils";

export function useAudit(id: string | undefined) {
  return useQuery({
    queryKey: ["audit", id],
    queryFn: () => api.get<AuditDetail>(`audits/${id}`),
    refetchInterval: (q) => (q.state.data && ["na_fila", "executando"].includes(q.state.data.status) ? 2000 : false),
  });
}

export default function AuditPage() {
  const { id } = useParams();
  const { data: audit, isLoading, error, refetch } = useAudit(id);
  const [dimension, setDimension] = useState<Dimensao | null>(null);
  const [shotTab, setShotTab] = useState<"dobra" | "inteira">("dobra");
  const client = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();

  const rerunAi = useMutation({
    mutationFn: () => api.post(`audits/${id}/rerun_ai`),
    onSuccess: () => {
      toast("Análise de IA reenfileirada.");
      setTimeout(() => client.invalidateQueries({ queryKey: ["audit", id] }), 1500);
    },
  });
  const rerun = useMutation({
    mutationFn: () => api.post<{ audit_id: number }>(`audits/${id}/rerun`),
    onSuccess: (r) => navigate(`/auditorias/${r.audit_id}`),
  });

  const grouped = useMemo(() => {
    const list = (audit?.findings ?? []).filter((f) => f.status_revisao !== "descartado" && (!dimension || f.dimensao === dimension));
    const groups: Record<string, Finding[]> = {};
    for (const f of list) (groups[f.severidade] ??= []).push(f);
    return Object.entries(groups).sort(([a], [b]) => SEVERITIES[a as keyof typeof SEVERITIES].ordem - SEVERITIES[b as keyof typeof SEVERITIES].ordem);
  }, [audit, dimension]);

  if (isLoading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  const a = audit!;
  const running = a.status === "na_fila" || a.status === "executando";
  const art = (t: string) => a.artifacts.find((x) => x.tipo === t);
  const pending = a.findings.filter((f) => f.status_revisao === "pendente").length;
  const discarded = a.findings.filter((f) => f.status_revisao === "descartado").length;
  const aiStep = a.steps.find((s) => s.etapa === "ia");

  const primary = running ? null : a.status === "falhou" ? (
    <Button onClick={() => rerun.mutate()} loading={rerun.isPending}>
      <RefreshCw className="size-4" aria-hidden /> Tentar de novo
    </Button>
  ) : pending > 0 ? (
    <Link to={`/auditorias/${a.id}/revisao`}>
      <Button>
        <ClipboardCheck className="size-4" aria-hidden /> Revisar {pending} achado(s)
      </Button>
    </Link>
  ) : (
    <Link to={`/auditorias/${a.id}/relatorio`}>
      <Button>
        <FileBarChart className="size-4" aria-hidden /> {a.reports.length ? "Editar relatório" : "Gerar relatório"}
      </Button>
    </Link>
  );

  return (
    <>
      <PageHeader
        back={<Link to={`/leads/${a.company_id}`}>← {a.empresa}</Link>}
        title={`Auditoria de ${a.dominio}`}
        description={running ? "Em andamento — os resultados aparecem conforme cada etapa termina" : `${a.status === "falhou" ? "Falhou" : "Concluída"} em ${fmtDateTime(a.concluido_em)} · regras ${a.versao_regras || "—"}${a.versao_prompt ? ` · prompt ${a.versao_prompt}` : ""}`}
        actions={
          <>
            {!running && a.status === "concluida" && (
              <>
                <Link to={`/auditorias/${a.id}/comparativo`}>
                  <Button variant="outline">
                    <BarChart3 className="size-4" aria-hidden /> Comparativo
                  </Button>
                </Link>
                <Button variant="outline" onClick={() => rerun.mutate()} loading={rerun.isPending} title="Nova auditoria do mesmo site">
                  <RefreshCw className="size-4" aria-hidden /> Reauditar
                </Button>
              </>
            )}
            {primary}
          </>
        }
      />
      <PageBody>
        {(running || a.status === "falhou") && (
          <Card className="p-4">
            {a.erro && <p className="mb-3 rounded-md bg-bad-soft px-3 py-2 text-sm text-bad">{a.erro}</p>}
            <JobProgress steps={a.steps} />
          </Card>
        )}

        {a.status === "falhou" && <ManualAudit audit={a} />}
        {a.status === "concluida" && a.metricas.manual && (
          <p className="rounded-md bg-surface-2 px-4 py-2 text-sm text-muted">
            Auditoria manual: o site bloqueou o robô, então as capturas e os achados foram registrados pelo analista e não há nota automática.
          </p>
        )}

        {a.status === "concluida" && (
          <>
            <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
              <Card className="flex flex-col items-center justify-center gap-3 p-4">
                <ScoreGauge score={a.nota_geral} label="Nota geral" />
                <div className="w-full space-y-1 text-xs text-muted">
                  <Metric label="Conteúdo no celular (LCP)" value={fmtSeconds(a.metricas.lcp_mobile_ms)} />
                  <Metric label="Peso da página" value={fmtBytes(a.metricas.peso_bytes)} />
                  <Metric label="HTTPS" value={a.metricas.https ? "Sim" : a.metricas.https === false ? "Não" : "—"} />
                  <Metric label="Plataforma" value={a.metricas.cms ?? "—"} />
                  <Metric label="Páginas rastreadas" value={String(a.metricas.paginas_rastreadas ?? "—")} />
                </div>
              </Card>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {a.dimensoes.map((d) => (
                  <DimensionCard key={d.chave} dim={d} active={dimension === d.chave} onClick={() => setDimension((cur) => (cur === d.chave ? null : d.chave))} />
                ))}
              </div>
            </div>

            <div className="grid gap-4 xl:grid-cols-[1fr_minmax(0,1.1fr)]">
              <Card>
                <CardHeader
                  title={dimension ? `Achados — ${a.dimensoes.find((d) => d.chave === dimension)?.nome}` : "Achados"}
                  description={`${a.findings.length - discarded} ativos${discarded ? ` · ${discarded} descartados` : ""}${pending ? ` · ${pending} pendentes de revisão` : ""}`}
                  actions={dimension && <Button variant="ghost" size="sm" onClick={() => setDimension(null)}>Ver todos</Button>}
                />
                <div className="space-y-4 p-4">
                  {grouped.length === 0 && <p className="text-sm text-muted">Nenhum achado nesta dimensão.</p>}
                  {grouped.map(([sev, list]) => (
                    <section key={sev}>
                      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                        Severidade {SEVERITIES[sev as keyof typeof SEVERITIES].nome} · {list.length}
                      </h3>
                      <div className="space-y-2">
                        {list.map((f) => (
                          <FindingItem key={f.id} finding={f} onSelect={() => navigate(`/auditorias/${a.id}/revisao?achado=${f.id}`)} />
                        ))}
                      </div>
                    </section>
                  ))}
                  {aiStep && aiStep.status !== "ok" && (
                    <div className="flex items-center justify-between gap-3 rounded-md border border-dashed border-border px-3 py-2 text-xs text-muted">
                      <span>
                        <Sparkles className="mr-1 inline size-3.5" aria-hidden />
                        Análise qualitativa por IA: {aiStep.erro || aiStep.status}
                      </span>
                      <Button size="sm" variant="outline" onClick={() => rerunAi.mutate()} loading={rerunAi.isPending}>
                        Rodar IA
                      </Button>
                    </div>
                  )}
                </div>
              </Card>

              <Card>
                <CardHeader
                  title="Capturas"
                  description="Desktop 1440 px e celular 390 px"
                  actions={
                    <div className="flex items-center gap-1">
                      <UploadCapture auditId={a.id} kind="desktop" label="Enviar desktop" />
                      <UploadCapture auditId={a.id} kind="mobile" label="Enviar celular" />
                    <Tabs
                      value={shotTab}
                      onChange={setShotTab}
                      items={[
                        { value: "dobra", label: "Primeira tela" },
                        { value: "inteira", label: "Página inteira" },
                      ]}
                    />
                    </div>
                  }
                />
                <div className="grid grid-cols-[1fr_minmax(0,0.38fr)] gap-3 p-4">
                  <ScreenshotAnnotated
                    artifact={art(shotTab === "dobra" ? "screenshot_desktop" : "screenshot_desktop_full")}
                    boxes={shotTab === "inteira" ? a.findings.filter((f) => f.evidencia.artefato === "screenshot_desktop_full" && f.status_revisao !== "descartado").flatMap((f) => f.evidencia.caixas ?? []) : []}
                    alt="Captura do site no computador"
                  />
                  <ScreenshotAnnotated
                    artifact={art(shotTab === "dobra" ? "screenshot_mobile" : "screenshot_mobile_full")}
                    boxes={shotTab === "inteira" ? a.findings.filter((f) => f.evidencia.artefato === "screenshot_mobile_full" && f.status_revisao !== "descartado").flatMap((f) => f.evidencia.caixas ?? []) : []}
                    alt="Captura do site no celular"
                  />
                </div>
              </Card>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader title="Etapas da auditoria" description="O que foi e o que não pôde ser medido" />
                <div className="p-4">
                  <JobProgress steps={a.steps} />
                </div>
              </Card>
              <Card>
                <CardHeader title="Tecnologias detectadas" />
                <div className="flex flex-wrap gap-1.5 p-4">
                  {a.website.tecnologias.length === 0 && <p className="text-sm text-muted">Nenhuma tecnologia identificada.</p>}
                  {a.website.tecnologias.map((t) => (
                    <Badge key={t.nome} className={t.desatualizado ? "bg-bad-soft text-bad" : "bg-surface-2 text-fg"}>
                      {t.nome}
                      {t.versao && ` ${t.versao}`}
                      {t.desatualizado && " · desatualizado"}
                    </Badge>
                  ))}
                </div>
                {a.metricas.lighthouse && (
                  <div className="border-t border-border p-4 text-xs">
                    <p className="mb-2 font-medium">Lighthouse</p>
                    {Object.entries(a.metricas.lighthouse).map(([preset, scores]) => (
                      <p key={preset} className="text-muted">
                        <span className="inline-block w-16 capitalize text-fg">{preset}</span>
                        {Object.entries(scores)
                          .map(([k, v]) => `${k} ${v}`)
                          .join(" · ")}
                      </p>
                    ))}
                  </div>
                )}
              </Card>
            </div>
          </>
        )}
      </PageBody>
    </>
  );
}

function UploadCapture({ auditId, kind, label }: { auditId: number; kind: "desktop" | "mobile"; label: string }) {
  const client = useQueryClient();
  const toast = useToast();
  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("tipo", kind);
      fd.append("arquivo", file);
      return api.post(`audits/${auditId}/upload_capture`, fd);
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["audit", String(auditId)] });
      toast("Captura enviada.");
    },
    onError: (e) => toast(e.message, "error"),
  });
  return (
    <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 text-xs font-medium hover:bg-surface-2" title="PNG, JPG ou WEBP até 10 MB">
      {upload.isPending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <Upload className="size-3.5" aria-hidden />}
      {label}
      <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
    </label>
  );
}

function ManualAudit({ audit }: { audit: AuditDetail }) {
  const client = useQueryClient();
  const toast = useToast();
  const finish = useMutation({
    mutationFn: () => api.post(`audits/${audit.id}/finish_manual`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["audit", String(audit.id)] });
      toast("Auditoria concluída como manual. Adicione os achados na revisão.");
    },
    onError: (e) => toast(e.message, "error"),
  });
  const shot = (t: string) => audit.artifacts.find((x) => x.tipo === t);
  return (
    <Card>
      <CardHeader
        title="Fazer a auditoria manualmente"
        description="Quando o site bloqueia o robô (Cloudflare, captcha), registre as capturas, conclua como manual e adicione os achados na revisão. O relatório sai normalmente, sem nota automática."
        actions={
          <Button onClick={() => finish.mutate()} loading={finish.isPending}>
            Concluir como auditoria manual
          </Button>
        }
      />
      <div className="grid gap-4 p-4 sm:grid-cols-2">
        {(["desktop", "mobile"] as const).map((kind) => (
          <div key={kind} className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{kind === "desktop" ? "Captura do computador" : "Captura do celular"}</span>
              <UploadCapture auditId={audit.id} kind={kind} label="Enviar" />
            </div>
            <ScreenshotAnnotated artifact={shot(`screenshot_${kind}`)} alt={`Captura ${kind} enviada pelo analista`} maxHeight={260} />
          </div>
        ))}
      </div>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span>{label}</span>
      <span className="font-medium text-fg">{value}</span>
    </div>
  );
}
