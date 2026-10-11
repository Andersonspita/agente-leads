import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Eye, FileCheck2, Radar, Search, UserPlus } from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { Capabilities, Dashboard } from "@/api/types";
import { PageBody, PageHeader } from "@/components/Layout";
import { StatusPill } from "@/components/domain";
import { Button, Card, CardHeader, EmptyState, ErrorState, Loading } from "@/components/ui";
import { fmtDateTime, fmtMoney } from "@/lib/utils";

const ACTIONS: Record<string, string> = {
  login: "entrou no sistema",
  busca_criada: "criou uma busca",
  auditoria_solicitada: "solicitou auditoria",
  achado_confirmado: "confirmou um achado",
  achado_descartado: "descartou um achado",
  achado_pendente: "editou um achado",
  achado_manual: "adicionou um achado",
  relatorio_gerado: "gerou relatório",
  relatorio_editado: "editou relatório",
  relatorio_enviado: "marcou relatório como enviado",
  relatorio_revogado: "revogou link de relatório",
  briefing_gerado: "gerou briefing",
  status_lead: "mudou status de lead",
  empresa_cadastrada: "cadastrou empresa",
  empresa_excluida: "excluiu empresa (LGPD)",
  pesos_alterados: "alterou pesos de categoria",
};

export default function DashboardPage() {
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<Dashboard>("dashboard"),
    refetchInterval: 15_000,
  });
  const caps = useQuery({ queryKey: ["capabilities"], queryFn: () => api.get<Capabilities>("settings/capabilities") });

  const totalLeads = data?.funil.reduce((a, b) => a + b.total, 0) ?? 0;

  return (
    <>
      <PageHeader
        title="Painel"
        description="Funil de vendas, auditorias em andamento e custos do mês"
        actions={
          <Link to="/buscas/nova">
            <Button>
              <Search className="size-4" aria-hidden /> Nova busca
            </Button>
          </Link>
        }
      />
      <PageBody>
        {isLoading && <Loading />}
        {error && <ErrorState error={error} onRetry={refetch} />}
        {caps.data && <MissingIntegrations caps={caps.data} />}
        {data && totalLeads === 0 && (
          <Card>
            <EmptyState
              icon={Search}
              title="Nenhum lead ainda"
              description="Comece buscando empresas de uma categoria numa cidade — por exemplo, clínicas odontológicas em Vitória da Conquista/BA. Ou cadastre uma URL avulsa em Leads."
              action={
                <Link to="/buscas/nova">
                  <Button>Fazer a primeira busca</Button>
                </Link>
              }
            />
          </Card>
        )}
        {data && totalLeads > 0 && (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat icon={UserPlus} label="Leads novos (7 dias)" value={data.semana.leads_novos} />
              <Stat icon={Radar} label="Auditorias concluídas (7 dias)" value={data.semana.auditorias} />
              <Stat icon={FileCheck2} label="Relatórios enviados (7 dias)" value={data.semana.relatorios_enviados} />
              <Stat icon={Eye} label="Relatórios abertos (7 dias)" value={data.semana.relatorios_abertos} />
            </div>

            <Card>
              <CardHeader title="Funil" description="Leads por status" />
              <div className="grid grid-cols-2 gap-2 p-4 sm:grid-cols-4 lg:grid-cols-8">
                {data.funil.map((f) => (
                  <Link key={f.status} to={`/leads?status=${f.status}`} className="rounded-md border border-border p-3 hover:border-brand/60">
                    <StatusPill status={f.status} />
                    <p className="mt-2 text-2xl font-bold tabular-nums">{f.total}</p>
                  </Link>
                ))}
              </div>
            </Card>
          </>
        )}

        {data && (
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader
                title="Auditorias em andamento"
                actions={
                  data.revisao_pendente > 0 && (
                    <Link to="/auditorias?revisao=pendente" className="text-xs font-medium text-brand hover:underline">
                      {data.revisao_pendente} aguardando revisão →
                    </Link>
                  )
                }
              />
              {data.auditorias_em_andamento.length === 0 ? (
                <p className="px-4 py-6 text-sm text-muted">Nenhuma auditoria na fila agora.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {data.auditorias_em_andamento.map((a) => (
                    <li key={a.id}>
                      <Link to={`/auditorias/${a.id}`} className="flex items-center justify-between px-4 py-2.5 hover:bg-surface-2">
                        <span className="font-medium">{a.empresa}</span>
                        <span className="flex items-center gap-2 text-xs text-muted">
                          {a.status === "executando" ? "Executando" : "Na fila"} <ArrowRight className="size-3.5" />
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card>
              <CardHeader title="Custo de APIs no mês" description="Google Places e Claude" />
              <div className="space-y-3 p-4">
                <p className="text-2xl font-bold tabular-nums">
                  {fmtMoney(data.custos.gasto_mes)}
                  <span className="ml-1 text-sm font-normal text-muted">de {fmtMoney(data.custos.teto_mes)}</span>
                </p>
                <div className="h-2 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={data.custos.percentual} aria-valuemin={0} aria-valuemax={100}>
                  <div className={data.custos.alerta ? "h-full bg-weak" : "h-full bg-brand"} style={{ width: `${Math.min(data.custos.percentual, 100)}%` }} />
                </div>
                {data.custos.alerta && (
                  <p className="flex items-center gap-1.5 text-xs text-weak">
                    <AlertTriangle className="size-3.5" /> Acima de 80% do teto mensal
                  </p>
                )}
                <ul className="space-y-1 text-xs text-muted">
                  {data.custos.por_provedor.map((p) => (
                    <li key={p.provedor} className="flex justify-between">
                      <span>
                        {p.provedor} · {p.chamadas} chamadas
                      </span>
                      <span className="tabular-nums">{fmtMoney(p.total)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </Card>
          </div>
        )}

        {data && data.atividade.length > 0 && (
          <Card>
            <CardHeader title="Atividade recente" description="Trilha de auditoria das ações da equipe" />
            <ul className="divide-y divide-border text-sm">
              {data.atividade.map((a, i) => (
                <li key={i} className="flex justify-between gap-4 px-4 py-2">
                  <span>
                    <strong className="font-medium">{a.usuario || "Sistema"}</strong> {ACTIONS[a.acao] ?? a.acao}
                    {a.entidade_id && <span className="text-muted"> · {a.entidade} #{a.entidade_id}</span>}
                  </span>
                  <span className="shrink-0 text-xs text-muted">{fmtDateTime(a.quando)}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </PageBody>
    </>
  );
}

function Stat({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: number }) {
  return (
    <Card className="flex items-center gap-3 p-4">
      <div className="rounded-md bg-brand/10 p-2 text-brand">
        <Icon className="size-5" strokeWidth={1.75} aria-hidden />
      </div>
      <div>
        <p className="text-2xl font-bold tabular-nums">{value}</p>
        <p className="text-xs text-muted">{label}</p>
      </div>
    </Card>
  );
}

function MissingIntegrations({ caps }: { caps: Capabilities }) {
  const missing = [
    !caps.base_cnpj && "base CNPJ (fonte gratuita principal; rode import_cnpj)",
    !caps.ia && "IA da análise qualitativa (GEMINI_API_KEY gratuita)",
    !caps.lighthouse && "Lighthouse",
    !caps.navegador && "Playwright/Chromium (capturas)",
  ].filter(Boolean) as string[];
  if (!missing.length) return null;
  return (
    <div className="flex items-start gap-2 rounded-md border border-weak/30 bg-weak-soft px-4 py-2.5 text-xs text-weak">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <p>
        Integrações não configuradas: {missing.join(", ")}. As etapas correspondentes aparecem como “não medidas”.{" "}
        <Link to="/configuracoes" className="underline">
          Ver configurações
        </Link>
      </p>
    </div>
  );
}
