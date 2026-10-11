import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Plus, Trash2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "@/api/client";
import type { Brand, Capabilities, Category, ChecklistItem, Dimensao, PromptVersion, RuleRow, UserRow } from "@/api/types";
import { useAuth } from "@/auth";
import { PageBody, PageHeader } from "@/components/Layout";
import { SeverityBadge } from "@/components/domain";
import { useToast } from "@/components/toast";
import { Badge, Button, Card, CardHeader, Checkbox, Dialog, Field, Input, Loading, Select, Tabs, Textarea } from "@/components/ui";
import { DIMENSIONS, DIMENSION_ORDER } from "@/lib/labels";
import { cn, fmtDateTime, fmtMoney } from "@/lib/utils";

type Tab = "categorias" | "marca" | "regras" | "prompts" | "usuarios" | "integracoes";

export default function SettingsPage() {
  const { me } = useAuth();
  const admin = !!me?.user?.is_admin;
  const [tab, setTab] = useState<Tab>("categorias");
  const items: { value: Tab; label: string }[] = [
    { value: "categorias", label: "Categorias e pesos" },
    { value: "marca", label: "Marca do relatório" },
    { value: "regras", label: "Regras" },
    ...(admin
      ? [
          { value: "prompts" as Tab, label: "Prompts de IA" },
          { value: "usuarios" as Tab, label: "Usuários" },
        ]
      : []),
    { value: "integracoes", label: "Integrações e custos" },
  ];
  return (
    <>
      <PageHeader title="Configurações" description={admin ? "Administração do sistema" : "Somente o Administrador altera estas configurações"} />
      <PageBody>
        <Tabs value={tab} onChange={setTab} items={items} />
        {tab === "categorias" && <CategoriesTab admin={admin} />}
        {tab === "marca" && <BrandTab admin={admin} />}
        {tab === "regras" && <RulesTab admin={admin} />}
        {tab === "prompts" && admin && <PromptsTab />}
        {tab === "usuarios" && admin && <UsersTab />}
        {tab === "integracoes" && <IntegrationsTab admin={admin} />}
      </PageBody>
    </>
  );
}

function CategoriesTab({ admin }: { admin: boolean }) {
  const { data, isLoading } = useQuery({ queryKey: ["categories"], queryFn: () => api.get<Category[]>("categories") });
  const [selected, setSelected] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const category = data?.find((c) => c.id === selected) ?? data?.[0];
  if (isLoading) return <Loading />;
  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
      <Card>
        <CardHeader title="Categorias" actions={admin && <Button size="sm" variant="outline" onClick={() => setCreating(true)}><Plus className="size-3.5" /> Nova</Button>} />
        <ul className="p-1">
          {data?.map((c) => (
            <li key={c.id}>
              <button onClick={() => setSelected(c.id)} className={cn("flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm", category?.id === c.id ? "bg-brand/10 text-brand dark:text-blue-300" : "hover:bg-surface-2")}>
                {c.nome}
                {!c.ativo && <Badge className="bg-surface-2 text-muted">inativa</Badge>}
              </button>
            </li>
          ))}
        </ul>
      </Card>
      {category && <CategoryEditor key={category.id} category={category} admin={admin} />}
      <NewCategoryDialog open={creating} onClose={() => setCreating(false)} onCreated={(c) => setSelected(c.id)} />
    </div>
  );
}

function CategoryEditor({ category, admin }: { category: Category; admin: boolean }) {
  const client = useQueryClient();
  const toast = useToast();
  const [weights, setWeights] = useState(() => Object.fromEntries(DIMENSION_ORDER.map((d) => [d, Math.round(category.pesos[d] * 100)])) as Record<Dimensao, number>);
  const [terms, setTerms] = useState(category.termos_busca.join(", "));
  const [cnaes, setCnaes] = useState(category.cnaes.join(", "));
  const [osmTags, setOsmTags] = useState(category.osm_tags.join(", "));
  const [item, setItem] = useState({ item: "", tipo: "secao" as ChecklistItem["tipo"], obrigatorio: true });
  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  const invalidate = () => client.invalidateQueries({ queryKey: ["categories"] });
  const onError = (e: Error) => toast(e.message, "error");

  const saveWeights = useMutation({
    mutationFn: () => api.put(`categories/${category.id}/weights`, Object.fromEntries(Object.entries(weights).map(([k, v]) => [k, v / 100]))),
    onSuccess: () => {
      invalidate();
      toast("Pesos salvos. Valem para as próximas auditorias.");
    },
    onError,
  });
  const saveInfo = useMutation({
    mutationFn: (extra: Partial<Category> = {}) =>
      api.patch(`categories/${category.id}`, {
        termos_busca: terms.split(",").map((t) => t.trim()).filter(Boolean),
        cnaes: cnaes.split(",").map((t) => t.trim()).filter(Boolean),
        osm_tags: osmTags.split(",").map((t) => t.trim()).filter(Boolean),
        ...extra,
      }),
    onSuccess: () => {
      invalidate();
      toast("Categoria salva.");
    },
    onError,
  });
  const addItem = useMutation({ mutationFn: () => api.post(`categories/${category.id}/checklist`, item), onSuccess: () => { setItem({ ...item, item: "" }); invalidate(); }, onError });
  const delItem = useMutation({ mutationFn: (itemId: number) => api.del(`categories/${category.id}/checklist/${itemId}`), onSuccess: invalidate });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title={category.nome} description="Termos da busca do Google, CNAEs da base da Receita e tags do OpenStreetMap" actions={admin && <Button size="sm" variant="ghost" onClick={() => saveInfo.mutate({ ativo: !category.ativo })}>{category.ativo ? "Desativar" : "Ativar"}</Button>} />
        <div className="grid gap-3 p-4 sm:grid-cols-2">
          <Field label="Termos de busca (separados por vírgula)" htmlFor="c-terms">
            <Input id="c-terms" disabled={!admin} value={terms} onChange={(e) => setTerms(e.target.value)} />
          </Field>
          <Field label="CNAEs (ex.: 8630-5/04)" htmlFor="c-cnae">
            <Input id="c-cnae" disabled={!admin} value={cnaes} onChange={(e) => setCnaes(e.target.value)} />
          </Field>
          <Field label="Tags do OpenStreetMap (chave=valor, separadas por vírgula)" htmlFor="c-osm" hint="Ex.: amenity=dentist, healthcare=dentist">
            <Input id="c-osm" disabled={!admin} value={osmTags} onChange={(e) => setOsmTags(e.target.value)} />
          </Field>
          {admin && (
            <div className="sm:col-span-2 flex justify-end">
              <Button size="sm" onClick={() => saveInfo.mutate({})} loading={saveInfo.isPending}>Salvar</Button>
            </div>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Pesos por dimensão"
          description="Nota = Σ peso × nota da dimensão. Os pesos precisam somar 100%."
          actions={admin && <Button size="sm" disabled={total !== 100} loading={saveWeights.isPending} onClick={() => saveWeights.mutate()}>Salvar pesos</Button>}
        />
        <div className="grid gap-3 p-4 sm:grid-cols-2">
          {DIMENSION_ORDER.map((d) => {
            const Icon = DIMENSIONS[d].icon;
            return (
              <label key={d} className="flex items-center gap-3 text-sm">
                <Icon className="size-4 text-muted" aria-hidden />
                <span className="w-28">{DIMENSIONS[d].nome}</span>
                <input type="range" min={0} max={40} step={5} disabled={!admin} value={weights[d]} onChange={(e) => setWeights({ ...weights, [d]: Number(e.target.value) })} className="flex-1 accent-brand" aria-label={`Peso de ${DIMENSIONS[d].nome}`} />
                <span className="w-10 text-right tabular-nums">{weights[d]}%</span>
              </label>
            );
          })}
        </div>
        <p className={cn("border-t border-border px-4 py-2 text-xs", total === 100 ? "text-good" : "text-bad")}>Soma: {total}%{total !== 100 && " — ajuste para 100%"}</p>
      </Card>

      <Card>
        <CardHeader title="Checklist mínimo da categoria" description="Entra no briefing do site novo e em regras específicas (ex.: agendamento online)" />
        <ul className="divide-y divide-border text-sm">
          {category.checklist.map((c) => (
            <li key={c.id} className="flex items-center justify-between gap-2 px-4 py-2">
              <span>
                {c.item} <Badge className="ml-1 bg-surface-2 text-muted">{c.tipo}</Badge> {!c.obrigatorio && <Badge className="bg-surface-2 text-muted">opcional</Badge>}
              </span>
              {admin && (
                <button className="rounded p-1 text-muted hover:text-bad" aria-label={`Remover ${c.item}`} onClick={() => delItem.mutate(c.id)}>
                  <Trash2 className="size-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
        {admin && (
          <div className="flex flex-wrap gap-2 border-t border-border p-3">
            <Input className="min-w-52 flex-1" placeholder="Novo item" value={item.item} onChange={(e) => setItem({ ...item, item: e.target.value })} aria-label="Novo item do checklist" />
            <Select className="w-36" value={item.tipo} onChange={(e) => setItem({ ...item, tipo: e.target.value as ChecklistItem["tipo"] })} aria-label="Tipo">
              <option value="pagina">Página</option>
              <option value="secao">Seção</option>
              <option value="integracao">Integração</option>
              <option value="meta">Meta</option>
            </Select>
            <label className="flex items-center gap-1.5 text-sm">
              <Checkbox label="Obrigatório" checked={item.obrigatorio} onChange={(v) => setItem({ ...item, obrigatorio: v })} /> Obrigatório
            </label>
            <Button variant="outline" disabled={!item.item} onClick={() => addItem.mutate()} loading={addItem.isPending}>Adicionar</Button>
          </div>
        )}
      </Card>
    </div>
  );
}

function NewCategoryDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (c: Category) => void }) {
  const client = useQueryClient();
  const [form, setForm] = useState({ nome: "", termos: "", cnaes: "" });
  const create = useMutation({
    mutationFn: () => api.post<Category>("categories", { nome: form.nome, termos_busca: form.termos.split(",").map((t) => t.trim()).filter(Boolean), cnaes: form.cnaes.split(",").map((t) => t.trim()).filter(Boolean) }),
    onSuccess: (c) => {
      client.invalidateQueries({ queryKey: ["categories"] });
      onCreated(c);
      onClose();
      setForm({ nome: "", termos: "", cnaes: "" });
    },
  });
  return (
    <Dialog open={open} onClose={onClose} title="Nova categoria" footer={<Button disabled={!form.nome} loading={create.isPending} onClick={() => create.mutate()}>Criar</Button>}>
      <div className="space-y-3">
        <Field label="Nome" htmlFor="nc-n"><Input id="nc-n" value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></Field>
        <Field label="Termos de busca" htmlFor="nc-t" hint="Separados por vírgula"><Input id="nc-t" value={form.termos} onChange={(e) => setForm({ ...form, termos: e.target.value })} /></Field>
        <Field label="CNAEs" htmlFor="nc-c"><Input id="nc-c" value={form.cnaes} onChange={(e) => setForm({ ...form, cnaes: e.target.value })} /></Field>
        {create.error && <p className="text-sm text-bad">{create.error.message}</p>}
      </div>
    </Dialog>
  );
}

function BrandTab({ admin }: { admin: boolean }) {
  const client = useQueryClient();
  const toast = useToast();
  const { data } = useQuery({ queryKey: ["brand"], queryFn: () => api.get<Brand>("settings/brand") });
  const [form, setForm] = useState<Brand | null>(null);
  const [logo, setLogo] = useState<File | null>(null);
  useEffect(() => {
    if (data) setForm(data);
  }, [data]);
  const save = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      const { logo: _logo, ...rest } = form!;
      Object.entries(rest).forEach(([k, v]) => fd.append(k, String(v)));
      if (logo) fd.append("logo", logo);
      return api.patch<Brand>("settings/brand", fd);
    },
    onSuccess: (b) => {
      client.setQueryData(["brand"], b);
      toast("Marca atualizada. Vale para os próximos relatórios e PDFs.");
    },
    onError: (e) => toast(e.message, "error"),
  });
  if (!form) return <Loading />;
  const set = (k: keyof Brand, v: string | boolean) => setForm({ ...form, [k]: v });
  return (
    <Card className="max-w-2xl">
      <CardHeader title="Marca que assina os relatórios" description="Nome, cor, logo e canais do CTA “falar com especialista”" />
      <div className="grid gap-3 p-4 sm:grid-cols-2">
        <Field label="Empresa" htmlFor="b-n"><Input id="b-n" disabled={!admin} value={form.nome_empresa} onChange={(e) => set("nome_empresa", e.target.value)} /></Field>
        <Field label="Cor principal" htmlFor="b-c">
          <div className="flex gap-2">
            <input type="color" disabled={!admin} value={form.cor_primaria} onChange={(e) => set("cor_primaria", e.target.value)} className="h-9 w-12 rounded border border-border" aria-label="Seletor de cor" />
            <Input id="b-c" disabled={!admin} value={form.cor_primaria} onChange={(e) => set("cor_primaria", e.target.value)} />
          </div>
        </Field>
        <Field label="WhatsApp (DDI + DDD + número)" htmlFor="b-w" hint="Ex.: 5577999998888"><Input id="b-w" disabled={!admin} value={form.whatsapp} onChange={(e) => set("whatsapp", e.target.value.replace(/\D/g, ""))} /></Field>
        <Field label="Link de agenda" htmlFor="b-a"><Input id="b-a" disabled={!admin} value={form.link_agenda} onChange={(e) => set("link_agenda", e.target.value)} /></Field>
        <Field label="E-mail de contato" htmlFor="b-e"><Input id="b-e" disabled={!admin} value={form.email_contato} onChange={(e) => set("email_contato", e.target.value)} /></Field>
        <Field label="Site" htmlFor="b-s"><Input id="b-s" disabled={!admin} value={form.site} onChange={(e) => set("site", e.target.value)} /></Field>
        <Field label="Logo" htmlFor="b-l" hint={form.logo ? "Logo atual cadastrado" : "PNG ou SVG, fundo transparente"}>
          <Input id="b-l" type="file" accept="image/*" disabled={!admin} onChange={(e) => setLogo(e.target.files?.[0] ?? null)} className="py-1.5" />
        </Field>
        <label className="flex items-center gap-2 self-end text-sm">
          <Checkbox label="Exibir nomes dos concorrentes por padrão" checked={form.exibir_nomes_concorrentes} onChange={(v) => set("exibir_nomes_concorrentes", v)} /> Exibir nomes dos concorrentes por padrão
        </label>
      </div>
      {admin && <div className="flex justify-end border-t border-border p-3"><Button loading={save.isPending} onClick={() => save.mutate()}>Salvar marca</Button></div>}
    </Card>
  );
}

function RulesTab({ admin }: { admin: boolean }) {
  const client = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["rules"], queryFn: () => api.get<RuleRow[]>("rules") });
  const toggle = useMutation({ mutationFn: (r: RuleRow) => api.patch(`rules/${r.id}`, { ativo: !r.ativo }), onSuccess: () => client.invalidateQueries({ queryKey: ["rules"] }) });
  if (isLoading) return <Loading />;
  return (
    <Card>
      <CardHeader title={`${data?.length ?? 0} regras automáticas`} description="Regras desativadas deixam de gerar achados e de contar na nota" />
      <table className="w-full text-sm">
        <tbody className="divide-y divide-border">
          {data?.map((r) => (
            <tr key={r.id} className={r.ativo ? "" : "opacity-50"}>
              <td className="px-4 py-2 font-mono text-xs">{r.codigo}</td>
              <td className="px-2 py-2 text-xs text-muted">{r.dimensao_nome}</td>
              <td className="px-2 py-2">{r.descricao.replace(/\{[^}]+\}/g, "…")}</td>
              <td className="px-2 py-2"><SeverityBadge severity={r.severidade_padrao} /></td>
              <td className="px-4 py-2 text-right">
                <Button size="sm" variant="ghost" disabled={!admin} onClick={() => toggle.mutate(r)}>{r.ativo ? "Desativar" : "Ativar"}</Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function PromptsTab() {
  const client = useQueryClient();
  const toast = useToast();
  const caps = useQuery({ queryKey: ["capabilities"], queryFn: () => api.get<Capabilities>("settings/capabilities") });
  const { data } = useQuery({ queryKey: ["prompts"], queryFn: () => api.get<PromptVersion[]>("prompts") });
  const [text, setText] = useState("");
  const create = useMutation({
    mutationFn: () => api.post("prompts", { nome: "analise_qualitativa", texto: text, modelo: caps.data?.modelo_ia ?? "", ativo: true }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["prompts"] });
      setText("");
      toast("Nova versão ativa. As próximas análises usam este prompt.");
    },
  });
  const activate = useMutation({ mutationFn: (p: PromptVersion) => api.patch(`prompts/${p.id}`, { ativo: true }), onSuccess: () => client.invalidateQueries({ queryKey: ["prompts"] }) });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader title="Nova versão do prompt de análise qualitativa" description="Variáveis: {empresa} {categoria} {cidade} {achados_regras} {texto}. Sem versão ativa, usa o prompt padrão do código." />
        <div className="space-y-3 p-4">
          <Textarea rows={14} value={text} onChange={(e) => setText(e.target.value)} className="font-mono text-xs" aria-label="Texto do prompt" />
          <div className="flex justify-end"><Button disabled={!text.trim()} loading={create.isPending} onClick={() => create.mutate()}>Salvar como versão ativa</Button></div>
        </div>
      </Card>
      <Card>
        <CardHeader title="Versões" description="Cada auditoria registra a versão usada, para comparar resultados" />
        <ul className="divide-y divide-border text-sm">
          {data?.length === 0 && <li className="px-4 py-6 text-muted">Usando o prompt padrão.</li>}
          {data?.map((p) => (
            <li key={p.id} className="space-y-1 px-4 py-3">
              <div className="flex items-center justify-between">
                <span className="font-medium">{p.nome} #{p.id} {p.ativo && <Badge className="ml-1 bg-good-soft text-good">ativa</Badge>}</span>
                {!p.ativo && <Button size="sm" variant="ghost" onClick={() => activate.mutate(p)}>Ativar</Button>}
              </div>
              <p className="text-xs text-muted">{p.modelo} · {fmtDateTime(p.criado_em)}</p>
              <details><summary className="cursor-pointer text-xs text-muted">Ver texto</summary><pre className="mt-1 whitespace-pre-wrap rounded bg-surface-2 p-2 text-xs">{p.texto}</pre></details>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function UsersTab() {
  const client = useQueryClient();
  const toast = useToast();
  const { data } = useQuery({ queryKey: ["users"], queryFn: () => api.get<{ results: UserRow[] }>("users") });
  const [form, setForm] = useState({ email: "", first_name: "", role: "analista", password: "" });
  const invalidate = () => client.invalidateQueries({ queryKey: ["users"] });
  const create = useMutation({ mutationFn: () => api.post("users", form), onSuccess: () => { invalidate(); setForm({ email: "", first_name: "", role: "analista", password: "" }); toast("Conta criada. O 2FA é configurado no primeiro login."); }, onError: (e) => toast(e.message, "error") });
  const toggle = useMutation({ mutationFn: (u: UserRow) => api.patch(`users/${u.id}`, { is_active: !u.is_active }), onSuccess: invalidate });
  const reset2fa = useMutation({ mutationFn: (u: UserRow) => api.post(`users/${u.id}/reset_2fa`), onSuccess: () => { invalidate(); toast("2FA resetado: o usuário configura de novo no próximo login."); } });
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
      <Card>
        <CardHeader title="Contas internas" description="Sem cadastro público; 2FA obrigatório" />
        <table className="w-full text-sm">
          <tbody className="divide-y divide-border">
            {data?.results.map((u) => (
              <tr key={u.id} className={u.is_active ? "" : "opacity-50"}>
                <td className="px-4 py-2"><p className="font-medium">{u.first_name || u.email}</p><p className="text-xs text-muted">{u.email}</p></td>
                <td className="px-2 py-2 text-xs">{u.role === "admin" ? "Administrador" : "Analista"}</td>
                <td className="px-2 py-2 text-xs">{u.has_2fa ? <span className="text-good">2FA ativo</span> : <span className="text-weak">2FA pendente</span>}</td>
                <td className="px-2 py-2 text-xs text-muted">{u.last_login ? `último acesso ${fmtDateTime(u.last_login)}` : "nunca acessou"}</td>
                <td className="px-4 py-2 text-right">
                  <Button size="sm" variant="ghost" onClick={() => reset2fa.mutate(u)}>Resetar 2FA</Button>
                  <Button size="sm" variant="ghost" onClick={() => toggle.mutate(u)}>{u.is_active ? "Desativar" : "Ativar"}</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card>
        <CardHeader title="Nova conta" />
        <div className="space-y-3 p-4">
          <Field label="Nome" htmlFor="u-n"><Input id="u-n" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} /></Field>
          <Field label="E-mail" htmlFor="u-e"><Input id="u-e" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label="Perfil" htmlFor="u-r"><Select id="u-r" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}><option value="analista">Analista</option><option value="admin">Administrador</option></Select></Field>
          <Field label="Senha inicial" htmlFor="u-p" hint="Mínimo de 10 caracteres"><Input id="u-p" type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
          <Button className="w-full" disabled={!form.email || form.password.length < 10} loading={create.isPending} onClick={() => create.mutate()}>Criar conta</Button>
        </div>
      </Card>
    </div>
  );
}

function IntegrationsTab({ admin }: { admin: boolean }) {
  const caps = useQuery({ queryKey: ["capabilities"], queryFn: () => api.get<Capabilities>("settings/capabilities") });
  const usage = useQuery({ queryKey: ["api-usage"], queryFn: () => api.get<{ provedor: string; endpoint: string; custo: number; data: string }[]>("api-usage"), enabled: admin });
  if (!caps.data) return <Loading />;
  const c = caps.data;
  const rows: [string, boolean, string][] = [
    ["Base aberta de CNPJ", c.base_cnpj, "Gratuita — python manage.py import_cnpj (empresas ativas por CNAE, inclusive sem site)"],
    ["Site pelo e-mail do CNPJ", c.email_cnpj, "Gratuita — testa o domínio do e-mail cadastral como site (EMAIL_DOMAIN_DISCOVERY)"],
    ["OpenStreetMap", c.osm, "Gratuita — API Overpass, filtrada pelo código IBGE (OSM_ENABLED)"],
    ["Google Places API (opcional, paga)", c.google_places, "GOOGLE_PLACES_API_KEY — maior cobertura, com nota e avaliações do Google"],
    ["Busca web complementar", c.busca_web, "GOOGLE_CSE_ID + GOOGLE_CSE_API_KEY — acha sites que o Places não trouxe"],
    ["IA da análise qualitativa", c.ia, c.ia ? `Ativa — ${c.modelo_ia}` : "GEMINI_API_KEY no .env (gratuito), ANTHROPIC_API_KEY ou IA local (AI_BASE_URL)"],
    ["Navegador (Playwright/Chromium)", c.navegador, "python -m playwright install chromium — capturas e métricas"],
    ["axe-core", c.axe, "npm install em backend/ — acessibilidade WCAG 2.1 AA"],
    ["Lighthouse", c.lighthouse, "npm install em backend/ ou LIGHTHOUSE_CMD — desempenho, SEO e boas práticas"],
    ["Filas Celery + Redis", c.filas_celery, "CELERY_BROKER_URL — sem ele, os jobs rodam em threads do servidor web"],
  ];
  const total = usage.data?.reduce((a, b) => a + b.custo, 0) ?? 0;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader title="Integrações" description="Configuradas por variáveis de ambiente no servidor" />
        <ul className="divide-y divide-border text-sm">
          {rows.map(([name, ok, hint]) => (
            <li key={name} className="flex items-start gap-3 px-4 py-2.5">
              {ok ? <CheckCircle2 className="mt-0.5 size-4 text-good" aria-label="Ativa" /> : <XCircle className="mt-0.5 size-4 text-muted" aria-label="Inativa" />}
              <div><p className="font-medium">{name}</p><p className="text-xs text-muted">{hint}</p></div>
            </li>
          ))}
        </ul>
      </Card>
      {admin && (
        <Card>
          <CardHeader title="Chamadas pagas (30 dias)" description={`Total estimado: ${fmtMoney(total)} · teto mensal em MONTHLY_API_BUDGET_BRL, alerta a 80%`} />
          <ul className="max-h-96 divide-y divide-border overflow-y-auto text-xs">
            {usage.data?.length === 0 && <li className="px-4 py-6 text-muted">Nenhuma chamada paga registrada.</li>}
            {usage.data?.map((u, i) => (
              <li key={i} className="flex justify-between px-4 py-1.5"><span>{u.provedor} · {u.endpoint}</span><span className="text-muted">{fmtMoney(u.custo)} · {fmtDateTime(u.data)}</span></li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
