import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { Comparison } from "@/api/types";
import { PageBody, PageHeader } from "@/components/Layout";
import { CompetitorBar, ScoreChip } from "@/components/domain";
import { Card, CardHeader, EmptyState, ErrorState, Loading } from "@/components/ui";
import { useAudit } from "./AuditPage";

export default function ComparePage() {
  const { id } = useParams();
  const audit = useAudit(id);
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["compare", id], queryFn: () => api.get<Comparison>(`audits/${id}/compare`) });

  return (
    <>
      <PageHeader back={<Link to={`/auditorias/${id}`}>← Auditoria</Link>} title="Comparativo local" description={audit.data ? `${audit.data.empresa} vs. concorrentes da mesma categoria e cidade` : undefined} />
      <PageBody>
        {isLoading && <Loading />}
        {error && <ErrorState error={error} onRetry={refetch} />}
        {data && data.total <= 1 && (
          <Card>
            <EmptyState icon={BarChart3} title="Ainda não há concorrentes auditados" description="Audite outras empresas da mesma categoria e cidade (a partir de uma busca) para montar o ranking local." />
          </Card>
        )}
        {data && data.total > 1 && (
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader title={`Posição ${data.posicao}º de ${data.total}`} description={`Linha tracejada = padrão de referência (${data.referencia}/100)`} />
              <div className="p-4">
                <CompetitorBar rows={data.linhas} reference={data.referencia} />
              </div>
            </Card>
            <Card>
              <CardHeader title="Resumo" />
              <dl className="space-y-3 p-4 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted">Nota do lead</dt>
                  <dd>
                    <ScoreChip score={data.linhas.find((l) => l.destaque)?.nota} />
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Maior nota local</dt>
                  <dd>
                    <ScoreChip score={data.maior_nota} />
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Média dos sites auditados na cidade</dt>
                  <dd>
                    <ScoreChip score={data.media_local} />
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Padrão de referência</dt>
                  <dd>
                    <ScoreChip score={data.referencia} />
                  </dd>
                </div>
              </dl>
              <ul className="border-t border-border p-4 text-xs text-muted">
                {data.linhas
                  .filter((l) => !l.destaque && l.audit_id)
                  .map((l) => (
                    <li key={l.audit_id}>
                      <Link to={`/auditorias/${l.audit_id}`} className="hover:text-brand">
                        {l.nome} ({l.dominio}) →
                      </Link>
                    </li>
                  ))}
              </ul>
            </Card>
          </div>
        )}
      </PageBody>
    </>
  );
}
