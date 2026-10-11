import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileText, Globe, Phone, Radar, Star, Trash2, Wand2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "@/api/client";
import type { AuditListItem, Briefing, CompanyDetail, LeadStatus, Page, Report } from "@/api/types";
import { PageBody, PageHeader } from "@/components/Layout";
import { ScoreChip, SiteStateIcon, StatusPill } from "@/components/domain";
import { useToast } from "@/components/toast";
import { Badge, Button, Card, CardHeader, Dialog, ErrorState, Input, Loading, Textarea } from "@/components/ui";
import { SITE_ORIGIN } from "@/lib/labels";
import { fmtDate, fmtDateTime, fmtPhone } from "@/lib/utils";

export default function CompanyPage() {
  const { id } = useParams();
  const client = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const company = useQuery({ queryKey: ["company", id], queryFn: () => api.get<CompanyDetail>(`companies/${id}`) });
  const audits = useQuery({
    queryKey: ["audits", { empresa: id }],
    queryFn: () => api.get<Page<AuditListItem>>(`audits?empresa=${id}`),
    refetchInterval: (q) => (q.state.data?.results.some((a) => a.status === "executando" || a.status === "na_fila") ? 3000 : false),
  });
  const reports = useQuery({ queryKey: ["reports", { empresa: id }], queryFn: () => api.get<Page<Report>>(`reports?empresa=${id}`) });
  const briefings = useQuery({ queryKey: ["briefings", { empresa: id }], queryFn: () => api.get<Page<Briefing>>(`briefings?empresa=${id}`) });
  const [note, setNote] = useState("");
  const [newSite, setNewSite] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const refresh = () => client.invalidateQueries({ queryKey: ["company", id] });
  const setStatus = useMutation({
    mutationFn: (status: LeadStatus) => api.patch(`companies/${id}`, { status_lead: status }),
    onSuccess: () => {
      refresh();
      client.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => toast(e.message, "error"),
  });
  const addNote = useMutation({
    mutationFn: () => api.post(`companies/${id}/notes`, { texto: note }),
    onSuccess: () => {
      setNote("");
      refresh();
    },
  });
  const addSite = useMutation({
    mutationFn: () => api.post(`companies/${id}/websites`, { url: /^https?:\/\//.test(newSite) ? newSite : `https://${newSite}` }),
    onSuccess: () => {
      setNewSite("");
      refresh();
    },
    onError: (e) => toast(e.message, "error"),
  });
  const audit = useMutation({
    mutationFn: (websiteId: number) => api.post<{ audit_ids: number[] }>("audits", { website_ids: [websiteId] }),
    onSuccess: (r) => navigate(`/auditorias/${r.audit_ids[0]}`),
    onError: (e) => toast(e.message, "error"),
  });
  const remove = useMutation({
    mutationFn: () => api.del(`companies/${id}`),
    onSuccess: () => {
      toast("Empresa e todos os dados coletados foram excluídos.");
      navigate("/leads");
    },
  });

  if (company.isLoading) return <Loading />;
  if (company.error) return <ErrorState error={company.error} onRetry={company.refetch} />;
  const c = company.data!;
  const main = c.websites[0];

  return (
    <>
      <PageHeader
        back={<Link to="/leads">← Leads</Link>}
        title={c.nome}
        description={
          <span className="inline-flex flex-wrap items-center gap-2">
            <StatusPill status={c.status_lead} /> {c.categoria || "Sem categoria"} · {c.municipio || "Cidade não informada"}
          </span>
        }
        actions={
          <>
            {main?.auditavel && (
              <Button onClick={() => audit.mutate(main.id)} loading={audit.isPending}>
                <Radar className="size-4" aria-hidden /> {main.ultima_auditoria ? "Reauditar" : "Auditar site"}
              </Button>
            )}
            <Link to={`/leads/${c.id}/site`}>
              <Button variant="outline">
                <Wand2 className="size-4" aria-hidden /> Site novo
              </Button>
            </Link>
            {(c.status_lead === "fechado" || c.status_lead === "entregue" || c.status_lead === "sem_site") && (
              <Link to={`/leads/${c.id}/briefing`}>
                <Button variant={main?.auditavel ? "outline" : "primary"}>
                  <FileText className="size-4" aria-hidden /> Briefing do site novo
                </Button>
              </Link>
            )}
          </>
        }
      />
      <PageBody className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader title="Funil" description="Mova o lead para a próxima etapa" />
            <div className="flex flex-wrap gap-2 p-4">
              {c.transicoes.length === 0 && <p className="text-sm text-muted">Etapa final do funil.</p>}
              {c.transicoes.map((t) => (
                <Button key={t.valor} variant="outline" size="sm" loading={setStatus.isPending && setStatus.variables === t.valor} onClick={() => setStatus.mutate(t.valor)}>
                  → {t.nome}
                </Button>
              ))}
            </div>
          </Card>

          <Card>
            <CardHeader title="Auditorias" description="Histórico por site (comparação no tempo)" />
            {audits.data?.results.length === 0 && <p className="px-4 py-6 text-sm text-muted">{main ? "Nenhuma auditoria ainda." : "Empresa sem site: vá direto para a proposta de site do zero."}</p>}
            <ul className="divide-y divide-border">
              {audits.data?.results.map((a) => (
                <li key={a.id}>
                  <Link to={`/auditorias/${a.id}`} className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-surface-2">
                    <span>
                      <span className="font-medium">{a.dominio}</span>
                      <span className="ml-2 text-xs text-muted">{fmtDateTime(a.concluido_em ?? a.criado_em)}</span>
                    </span>
                    <span className="flex items-center gap-2">
                      {a.pendentes > 0 && <Badge className="bg-weak-soft text-weak">{a.pendentes} para revisar</Badge>}
                      {a.status === "concluida" ? <ScoreChip score={a.nota_geral} /> : <Badge className="bg-surface-2 text-muted">{a.status === "falhou" ? "Falhou" : "Em andamento"}</Badge>}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader title="Relatórios e briefings" />
            <ul className="divide-y divide-border text-sm">
              {reports.data?.results.map((r) => (
                <li key={`r${r.id}`} className="flex items-center justify-between px-4 py-2.5">
                  <Link to={`/auditorias/${r.audit}/relatorio`} className="hover:text-brand">
                    Relatório de {fmtDate(r.criado_em)}
                  </Link>
                  <span className="text-xs text-muted">
                    {r.revogado ? "revogado" : r.enviado_em ? `enviado ${fmtDate(r.enviado_em)}` : "não enviado"} · {r.visualizacoes} aberturas
                  </span>
                </li>
              ))}
              {briefings.data?.results.map((b) => (
                <li key={`b${b.id}`} className="flex items-center justify-between px-4 py-2.5">
                  <Link to={`/leads/${c.id}/briefing`} className="hover:text-brand">
                    Briefing v{b.versao}
                  </Link>
                  <span className="text-xs text-muted">{fmtDate(b.criado_em)}</span>
                </li>
              ))}
              {!reports.data?.results.length && !briefings.data?.results.length && <li className="px-4 py-6 text-muted">Nada gerado ainda.</li>}
            </ul>
          </Card>

          <Card>
            <CardHeader title="Anotações" />
            <div className="space-y-3 p-4">
              <Textarea placeholder="Ex.: falei com a recepcionista, retornar na sexta…" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Nova anotação" />
              <div className="flex justify-end">
                <Button size="sm" disabled={!note.trim()} loading={addNote.isPending} onClick={() => addNote.mutate()}>
                  Adicionar anotação
                </Button>
              </div>
              <ul className="space-y-2">
                {c.notes.map((n) => (
                  <li key={n.id} className="rounded-md bg-surface-2 px-3 py-2 text-sm">
                    <p className="whitespace-pre-wrap">{n.texto}</p>
                    <p className="mt-1 text-xs text-muted">
                      {n.autor_nome} · {fmtDateTime(n.criado_em)}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Contato" />
            <dl className="space-y-2.5 p-4 text-sm">
              {c.telefone && (
                <Row icon={Phone} label="Telefone">
                  <a href={`tel:${c.telefone}`} className="hover:text-brand">
                    {fmtPhone(c.telefone)}
                  </a>
                </Row>
              )}
              {c.whatsapp && (
                <Row icon={Phone} label="WhatsApp">
                  <a href={`https://wa.me/55${c.whatsapp}`} target="_blank" rel="noreferrer" className="hover:text-brand">
                    {fmtPhone(c.whatsapp)}
                  </a>
                </Row>
              )}
              {c.endereco && <Row label="Endereço">{c.endereco}</Row>}
              {c.bairro && <Row label="Bairro">{c.bairro}</Row>}
              {c.cnpj && <Row label="CNPJ">{c.cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5")}</Row>}
              {c.nota_google && (
                <Row icon={Star} label="Google">
                  {Number(c.nota_google).toFixed(1).replace(".", ",")} ({c.n_avaliacoes} avaliações)
                </Row>
              )}
              {Object.entries(c.redes_sociais).map(([k, v]) => (
                <Row key={k} label={k}>
                  <a href={v} target="_blank" rel="noreferrer" className="break-all hover:text-brand">
                    {v.replace(/^https?:\/\//, "")}
                  </a>
                </Row>
              ))}
            </dl>
          </Card>

          <Card>
            <CardHeader title="Sites" />
            <ul className="divide-y divide-border">
              {c.websites.map((w) => (
                <li key={w.id} className="space-y-1 px-4 py-3 text-sm">
                  <a href={w.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 font-medium hover:text-brand">
                    <Globe className="size-3.5" aria-hidden /> {w.dominio} <ExternalLink className="size-3" aria-hidden />
                  </a>
                  <div className="flex flex-wrap gap-2 text-xs text-muted">
                    <SiteStateIcon state={w.online === false ? "fora_do_ar" : "tem_site"} />
                    {w.https !== null && <span>{w.https ? "HTTPS" : "sem HTTPS"}</span>}
                    {w.status_http && <span>HTTP {w.status_http}</span>}
                    {!w.auditavel && <span className="text-bad">bloqueia robô</span>}
                    {w.origem && <span>via {SITE_ORIGIN[w.origem] ?? w.origem}</span>}
                  </div>
                  {w.tecnologias.length > 0 && <p className="text-xs text-muted">{w.tecnologias.map((t) => `${t.nome}${t.versao ? ` ${t.versao}` : ""}`).join(" · ")}</p>}
                </li>
              ))}
            </ul>
            <div className="flex gap-2 border-t border-border p-3">
              <Input placeholder="Adicionar site" value={newSite} onChange={(e) => setNewSite(e.target.value)} aria-label="URL do site" />
              <Button variant="outline" disabled={!newSite} loading={addSite.isPending} onClick={() => addSite.mutate()}>
                Adicionar
              </Button>
            </div>
          </Card>

          <Button variant="ghost" className="w-full text-bad" onClick={() => setConfirmDelete(true)}>
            <Trash2 className="size-4" aria-hidden /> Excluir dados (pedido LGPD)
          </Button>
        </div>
      </PageBody>
      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="Excluir todos os dados desta empresa?"
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancelar
            </Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
              Excluir definitivamente
            </Button>
          </>
        }
      >
        <p className="text-sm">
          Remove a empresa, sites, auditorias, capturas de tela, relatórios (os links param de funcionar) e anotações. Use para atender pedidos de exclusão. A ação fica registrada na trilha de auditoria e não pode ser desfeita.
        </p>
      </Dialog>
    </>
  );
}

function Row({ label, icon: Icon, children }: { label: string; icon?: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[6rem_1fr] gap-2">
      <dt className="flex items-center gap-1 text-xs capitalize text-muted">
        {Icon && <Icon className="size-3" aria-hidden />} {label}
      </dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}
