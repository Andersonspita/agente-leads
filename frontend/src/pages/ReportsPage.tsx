import { useQuery } from "@tanstack/react-query";
import { FileBarChart } from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import type { Page, Report } from "@/api/types";
import { PageBody, PageHeader } from "@/components/Layout";
import { ScoreChip } from "@/components/domain";
import { Badge, Card, EmptyState, ErrorState, Loading } from "@/components/ui";
import { fmtDate, fmtDateTime } from "@/lib/utils";

export default function ReportsPage() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["reports", "all"], queryFn: () => api.get<Page<Report>>("reports") });

  return (
    <>
      <PageHeader title="Relatórios" description="Links enviados aos prospects e rastreio de abertura" />
      <PageBody>
        <Card>
          {isLoading && <Loading />}
          {error && <ErrorState error={error} onRetry={refetch} />}
          {data?.results.length === 0 && <EmptyState icon={FileBarChart} title="Nenhum relatório gerado" description="Depois de revisar os achados de uma auditoria, gere o link + PDF no editor do relatório." />}
          {!!data?.results.length && (
            <table className="w-full text-sm">
              <thead className="border-b border-border text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Empresa</th>
                  <th className="px-4 py-2 font-medium">Nota</th>
                  <th className="px-4 py-2 font-medium">Situação</th>
                  <th className="px-4 py-2 font-medium">Aberturas</th>
                  <th className="px-4 py-2 font-medium">Criado</th>
                  <th className="px-4 py-2 font-medium">Expira</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.results.map((r) => (
                  <tr key={r.id} className="hover:bg-surface-2">
                    <td className="px-4 py-2.5">
                      <Link to={`/auditorias/${r.audit}/relatorio`} className="font-medium hover:text-brand">
                        {r.empresa}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5">
                      <ScoreChip score={r.nota_geral} />
                    </td>
                    <td className="px-4 py-2.5">
                      {r.revogado ? (
                        <Badge className="bg-bad-soft text-bad">Revogado</Badge>
                      ) : !r.disponivel ? (
                        <Badge className="bg-surface-2 text-muted">Expirado</Badge>
                      ) : r.enviado_em ? (
                        <Badge className="bg-good-soft text-good">Enviado {fmtDate(r.enviado_em)}</Badge>
                      ) : (
                        <Badge className="bg-weak-soft text-weak">Não enviado</Badge>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {r.visualizacoes > 0 ? (
                        <span>
                          <strong>{r.visualizacoes}</strong> <span className="text-xs text-muted">· última {fmtDateTime(r.ultima_visualizacao)}</span>
                        </span>
                      ) : (
                        <span className="text-muted">Não aberto</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted">{fmtDate(r.criado_em)}</td>
                    <td className="px-4 py-2.5 text-xs text-muted">{fmtDate(r.expira_em)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </PageBody>
    </>
  );
}
