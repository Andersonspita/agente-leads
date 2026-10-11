import { useQuery } from "@tanstack/react-query";
import { Radar } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { api, qs } from "@/api/client";
import type { AuditListItem, Page } from "@/api/types";
import { PageBody, PageHeader } from "@/components/Layout";
import { ScoreChip } from "@/components/domain";
import { Badge, Card, EmptyState, ErrorState, Loading, Pagination, Select, Spinner } from "@/components/ui";
import { fmtDateTime } from "@/lib/utils";

const STATUS: Record<AuditListItem["status"], { nome: string; className: string }> = {
  na_fila: { nome: "Na fila", className: "bg-surface-2 text-muted" },
  executando: { nome: "Executando", className: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300" },
  concluida: { nome: "Concluída", className: "bg-good-soft text-good" },
  falhou: { nome: "Falhou", className: "bg-bad-soft text-bad" },
};

export default function AuditsPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const revisao = params.get("revisao") ?? "";
  const page = Number(params.get("page") ?? 1);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["audits", { status, revisao, page }],
    queryFn: () => api.get<Page<AuditListItem>>(`audits${qs({ status, revisao, page })}`),
    refetchInterval: (q) => (q.state.data?.results.some((a) => a.status === "executando" || a.status === "na_fila") ? 3000 : false),
  });
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    next.delete("page");
    setParams(next, { replace: true });
  };

  return (
    <>
      <PageHeader title="Auditorias" description="Fila, resultados e revisão de achados" />
      <PageBody>
        <Card>
          <div className="flex flex-wrap gap-2 border-b border-border p-3">
            <Select aria-label="Status" className="w-48" value={status} onChange={(e) => set("status", e.target.value)}>
              <option value="">Todos os status</option>
              <option value="na_fila,executando">Em andamento</option>
              <option value="concluida">Concluídas</option>
              <option value="falhou">Falharam</option>
            </Select>
            <Select aria-label="Revisão" className="w-56" value={revisao} onChange={(e) => set("revisao", e.target.value)}>
              <option value="">Qualquer revisão</option>
              <option value="pendente">Com achados pendentes</option>
            </Select>
          </div>
          {isLoading && <Loading />}
          {error && <ErrorState error={error} onRetry={refetch} />}
          {data?.results.length === 0 && <EmptyState icon={Radar} title="Nenhuma auditoria" description="Selecione empresas numa busca ou em Leads e clique em “Auditar selecionados”." />}
          {!!data?.results.length && (
            <>
              <table className="w-full text-sm">
                <thead className="border-b border-border text-left text-xs text-muted">
                  <tr>
                    <th className="px-4 py-2 font-medium">Empresa</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium">Nota</th>
                    <th className="px-4 py-2 font-medium">Revisão</th>
                    <th className="px-4 py-2 font-medium">Quando</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.results.map((a) => (
                    <tr key={a.id} className="hover:bg-surface-2">
                      <td className="px-4 py-2.5">
                        <Link to={`/auditorias/${a.id}`} className="font-medium hover:text-brand">
                          {a.empresa}
                        </Link>
                        <p className="text-xs text-muted">{a.dominio}</p>
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge className={STATUS[a.status].className}>
                          {a.status === "executando" && <Spinner className="size-3" />}
                          {STATUS[a.status].nome}
                          {a.status === "executando" && ` ${a.progresso.feitas}/${a.progresso.total}`}
                        </Badge>
                        {a.erro && <p className="mt-0.5 max-w-xs truncate text-xs text-bad" title={a.erro}>{a.erro}</p>}
                      </td>
                      <td className="px-4 py-2.5">
                        <ScoreChip score={a.nota_geral} />
                      </td>
                      <td className="px-4 py-2.5">
                        {a.pendentes > 0 ? (
                          <Link to={`/auditorias/${a.id}/revisao`} className="text-xs font-medium text-weak hover:underline">
                            {a.pendentes} pendente(s) →
                          </Link>
                        ) : (
                          <span className="text-xs text-muted">{a.status === "concluida" ? "Revisada" : "—"}</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted">{fmtDateTime(a.concluido_em ?? a.criado_em)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination page={page} count={data.count} onPage={(p) => setParams((prev) => { const n = new URLSearchParams(prev); n.set("page", String(p)); return n; })} />
            </>
          )}
        </Card>
      </PageBody>
    </>
  );
}
