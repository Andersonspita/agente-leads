import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Ban, Copy, Download, ExternalLink, Eye, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { Comparison, Page, Report } from "@/api/types";
import { PageHeader } from "@/components/Layout";
import { SeverityBadge } from "@/components/domain";
import { useToast } from "@/components/toast";
import { Badge, Button, Card, CardHeader, Checkbox, ErrorState, Field, Input, Loading, Textarea } from "@/components/ui";
import { SEVERITIES } from "@/lib/labels";
import { fmtDate, fmtDateTime } from "@/lib/utils";
import { useAudit } from "./AuditPage";

const TOP = 5;

export default function ReportEditorPage() {
  const { id } = useParams();
  const audit = useAudit(id);
  const client = useQueryClient();
  const toast = useToast();
  const reports = useQuery({
    queryKey: ["reports", { audit: id }],
    queryFn: () => api.get<Page<Report>>(`reports?audit=${id}`),
    select: (p) => p.results,
    refetchInterval: (q) => {
      const current = (q.state.data?.results ?? []).find((r) => !r.revogado);
      return current && ["pendente", "gerando"].includes(current.pdf_status) ? 2500 : false;
    },
  });
  const compare = useQuery({ queryKey: ["compare", id], queryFn: () => api.get<Comparison>(`audits/${id}/compare`) });
  const report = reports.data?.find((r) => !r.revogado);

  const confirmed = useMemo(
    () => (audit.data?.findings ?? []).filter((f) => f.status_revisao === "confirmado").sort((a, b) => SEVERITIES[a.severidade].ordem - SEVERITIES[b.severidade].ordem),
    [audit.data],
  );
  const [order, setOrder] = useState<number[]>([]);
  const [opening, setOpening] = useState("");
  const [summary, setSummary] = useState("");
  const [competitors, setCompetitors] = useState<number[]>([]);
  const [showNames, setShowNames] = useState(false);
  const [expires, setExpires] = useState("");
  const [previewKey, setPreviewKey] = useState(0);

  useEffect(() => {
    if (!audit.data || reports.isLoading) return;
    const ids = confirmed.map((f) => f.id);
    if (report) {
      const saved = report.achados_ids.filter((x) => ids.includes(x));
      setOrder([...saved, ...ids.filter((x) => !saved.includes(x))]);
      setOpening(report.texto_abertura);
      setSummary(report.resumo);
      setCompetitors(report.concorrentes_ids);
      setShowNames(report.exibir_nomes_concorrentes);
      setExpires(report.expira_em.slice(0, 10));
    } else {
      setOrder(ids);
      setOpening(`Olá! Analisamos o site da ${audit.data.empresa} com os mesmos critérios que o Google e os clientes usam. Abaixo estão os pontos que mais impedem o site de trazer novos contatos — e como resolvê-los.`);
    }
  }, [audit.data, report?.id, reports.isLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!report && compare.data && competitors.length === 0) {
      setCompetitors(compare.data.linhas.filter((l) => !l.destaque && l.company_id).map((l) => l.company_id!));
    }
  }, [compare.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const body = {
    audit: Number(id),
    texto_abertura: opening,
    resumo: summary,
    achados_ids: order,
    concorrentes_ids: competitors,
    exibir_nomes_concorrentes: showNames,
    ...(expires ? { expira_em: new Date(`${expires}T23:59:59`).toISOString() } : {}),
  };
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["reports"] });
    setPreviewKey((k) => k + 1);
  };
  const save = useMutation({
    mutationFn: () => (report ? api.patch<Report>(`reports/${report.id}`, body) : api.post<Report>("reports", body)),
    onSuccess: () => {
      toast(report ? "Relatório atualizado; PDF sendo regenerado." : "Link e PDF gerados.");
      refresh();
    },
    onError: (e) => toast(e.message, "error"),
  });
  const action = useMutation({
    mutationFn: (path: "revoke" | "mark_sent") => api.post<Report>(`reports/${report!.id}/${path}`, { canal: "whatsapp" }),
    onSuccess: (_r, path) => {
      toast(path === "revoke" ? "Link revogado." : "Marcado como enviado; lead avançou no funil.");
      refresh();
      client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  if (audit.isLoading || reports.isLoading) return <Loading />;
  if (audit.error) return <ErrorState error={audit.error} />;
  const a = audit.data!;
  const pending = a.findings.filter((f) => f.status_revisao === "pendente").length;
  const move = (i: number, d: -1 | 1) =>
    setOrder((o) => {
      const n = [...o];
      [n[i], n[i + d]] = [n[i + d], n[i]];
      return n;
    });
  const byId = Object.fromEntries(confirmed.map((f) => [f.id, f]));
  const shareText = report ? `Olá! Preparamos um diagnóstico gratuito do site da ${a.empresa}: ${report.url_publica}` : "";

  return (
    <div className="flex h-screen flex-col">
      <PageHeader
        back={<Link to={`/auditorias/${a.id}`}>← Auditoria de {a.dominio}</Link>}
        title="Editor do relatório"
        description={report ? `Link criado em ${fmtDate(report.criado_em)} · expira em ${fmtDate(report.expira_em)} · ${report.visualizacoes} abertura(s)${report.ultima_visualizacao ? `, última ${fmtDateTime(report.ultima_visualizacao)}` : ""}` : "Prepare o texto, a ordem dos achados e gere o link + PDF"}
        actions={
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={pending > 0}>
            {report ? "Salvar alterações" : "Gerar link + PDF"}
          </Button>
        }
      />
      {pending > 0 && (
        <p className="mx-6 mt-3 rounded-md bg-weak-soft px-3 py-2 text-sm text-weak">
          Há {pending} achado(s) pendente(s). <Link to={`/auditorias/${a.id}/revisao`} className="underline">Revise antes de gerar o relatório</Link> — achados de IA só entram após confirmação.
        </p>
      )}
      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(360px,0.8fr)_1.2fr]">
        <div className="min-h-0 space-y-4 overflow-y-auto border-r border-border p-4">
          {report && (
            <Card>
              <CardHeader title="Entrega" description={report.enviado_em ? `Enviado em ${fmtDateTime(report.enviado_em)}` : "Ainda não enviado"} />
              <div className="space-y-3 p-4">
                <div className="flex gap-2">
                  <Input readOnly value={report.url_publica} aria-label="Link público" onFocus={(e) => e.target.select()} />
                  <Button variant="outline" onClick={() => navigator.clipboard.writeText(report.url_publica).then(() => toast("Link copiado."))} title="Copiar link">
                    <Copy className="size-4" aria-label="Copiar" />
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  <a href={`https://wa.me/?text=${encodeURIComponent(shareText)}`} target="_blank" rel="noreferrer">
                    <Button size="sm" variant="outline">
                      <Send className="size-3.5" aria-hidden /> Abrir no WhatsApp
                    </Button>
                  </a>
                  <a href={report.url_publica} target="_blank" rel="noreferrer">
                    <Button size="sm" variant="outline">
                      <ExternalLink className="size-3.5" aria-hidden /> Abrir link
                    </Button>
                  </a>
                  {report.pdf_url && report.pdf_status === "pronto" ? (
                    <a href={report.pdf_url} target="_blank" rel="noreferrer">
                      <Button size="sm" variant="outline">
                        <Download className="size-3.5" aria-hidden /> PDF
                      </Button>
                    </a>
                  ) : (
                    <Badge className="bg-surface-2 text-muted">PDF: {report.pdf_status}</Badge>
                  )}
                </div>
                <div className="flex flex-wrap gap-2 border-t border-border pt-3">
                  {!report.enviado_em && (
                    <Button size="sm" onClick={() => action.mutate("mark_sent")} loading={action.isPending && action.variables === "mark_sent"}>
                      Marcar como enviado
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" className="text-bad" onClick={() => action.mutate("revoke")} loading={action.isPending && action.variables === "revoke"}>
                    <Ban className="size-3.5" aria-hidden /> Revogar link
                  </Button>
                </div>
              </div>
            </Card>
          )}

          <Card>
            <CardHeader title="Textos" />
            <div className="space-y-3 p-4">
              <Field label="Texto de abertura" htmlFor="r-open" hint="Tom construtivo: o dono da empresa vai ler.">
                <Textarea id="r-open" rows={4} value={opening} onChange={(e) => setOpening(e.target.value)} />
              </Field>
              <Field label="Resumo em 3 frases" htmlFor="r-sum" hint="Em branco = resumo automático a partir da nota e dos principais problemas.">
                <Textarea id="r-sum" rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />
              </Field>
              <Field label="Link expira em" htmlFor="r-exp" hint="Padrão: 60 dias">
                <Input id="r-exp" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} />
              </Field>
            </div>
          </Card>

          <Card>
            <CardHeader title="Ordem dos achados" description={`Os ${TOP} primeiros viram o “Top ${TOP} problemas”; o restante vai para o apêndice.`} />
            <ol className="divide-y divide-border">
              {order.map((fid, i) => {
                const f = byId[fid];
                if (!f) return null;
                return (
                  <li key={fid} className={i < TOP ? "flex items-center gap-2 bg-brand/5 px-3 py-2" : "flex items-center gap-2 px-3 py-2"}>
                    <span className="w-5 text-right text-xs font-semibold text-muted">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm">{f.titulo}</p>
                      <SeverityBadge severity={f.severidade} />
                    </div>
                    <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Subir">
                      <ArrowUp className="size-3.5" />
                    </Button>
                    <Button size="sm" variant="ghost" disabled={i === order.length - 1} onClick={() => move(i, 1)} aria-label="Descer">
                      <ArrowDown className="size-3.5" />
                    </Button>
                  </li>
                );
              })}
            </ol>
          </Card>

          <Card>
            <CardHeader title="Concorrentes" description="Até 5, da mesma categoria e cidade" />
            <div className="space-y-2 p-4 text-sm">
              {compare.data?.linhas.filter((l) => !l.destaque).length === 0 && <p className="text-muted">Nenhum concorrente auditado ainda.</p>}
              {compare.data?.linhas
                .filter((l) => !l.destaque && l.company_id)
                .map((l) => (
                  <label key={l.company_id} className="flex items-center gap-2">
                    <Checkbox
                      label={l.nome}
                      checked={competitors.includes(l.company_id!)}
                      onChange={(on) => setCompetitors((c) => (on ? [...c, l.company_id!].slice(0, 5) : c.filter((x) => x !== l.company_id)))}
                    />
                    {l.nome} <span className="text-muted">({l.nota})</span>
                  </label>
                ))}
              <label className="flex items-center gap-2 border-t border-border pt-2">
                <Checkbox label="Exibir nomes dos concorrentes" checked={showNames} onChange={setShowNames} />
                Exibir nomes dos concorrentes (senão: “Concorrente 1, 2…”)
              </label>
            </div>
          </Card>
        </div>

        <div className="flex min-h-0 flex-col bg-surface-2">
          <div className="flex items-center justify-between border-b border-border px-4 py-2 text-xs text-muted">
            <span className="flex items-center gap-1.5">
              <Eye className="size-3.5" aria-hidden /> Pré-visualização {report ? "(salve para atualizar)" : "(gere o relatório para visualizar)"}
            </span>
          </div>
          {report ? (
            <iframe key={previewKey} title="Pré-visualização do relatório" src={`/preview/relatorio/${report.id}`} className="min-h-0 w-full flex-1 bg-white" />
          ) : (
            <p className="p-8 text-center text-sm text-muted">A pré-visualização aparece depois de gerar o link.</p>
          )}
        </div>
      </div>
    </div>
  );
}
