import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, Plus, Users } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, ApiError, qs } from "@/api/client";
import type { Category, CompanyDetail, CompanyListItem, Municipality, Page } from "@/api/types";
import { CityPicker } from "@/components/CityPicker";
import { CompanyFilters, useFilters } from "@/components/CompanyFilters";
import { CompanyTable } from "@/components/CompanyTable";
import { PageBody, PageHeader } from "@/components/Layout";
import { Button, Card, Dialog, EmptyState, ErrorState, Field, Input, Loading, Pagination, Select } from "@/components/ui";
import { UFS } from "@/lib/labels";

export default function LeadsPage() {
  const filters = useFilters();
  const { values, page } = filters;
  const [adding, setAdding] = useState(false);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["companies", values],
    queryFn: () => api.get<Page<CompanyListItem>>(`companies${qs({ ...values, page })}`),
  });

  return (
    <>
      <PageHeader
        title="Leads"
        description="Todas as empresas prospectadas (CRM leve)"
        actions={
          <>
            <a href={`/api/companies/export${qs({ ...values, page: undefined })}`}>
              <Button variant="outline">
                <Download className="size-4" aria-hidden /> CSV
              </Button>
            </a>
            <Button onClick={() => setAdding(true)}>
              <Plus className="size-4" aria-hidden /> URL avulsa
            </Button>
          </>
        }
      />
      <PageBody>
        <Card>
          <CompanyFilters {...filters} />
          {isLoading && <Loading />}
          {error && <ErrorState error={error} onRetry={refetch} />}
          {data?.results.length === 0 && (
            <EmptyState icon={Users} title="Nenhum lead encontrado" description="Faça uma busca por categoria e cidade ou cadastre uma URL avulsa para auditar." action={<Button onClick={() => setAdding(true)}>Cadastrar URL avulsa</Button>} />
          )}
          {!!data?.results.length && (
            <>
              <CompanyTable rows={data.results} />
              <Pagination page={page} count={data.count} onPage={(p) => filters.set("page", String(p))} />
            </>
          )}
        </Card>
      </PageBody>
      <AddCompanyDialog open={adding} onClose={() => setAdding(false)} />
    </>
  );
}

function AddCompanyDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const categories = useQuery({ queryKey: ["categories", "ativas"], queryFn: () => api.get<Category[]>("categories?ativas=1") });
  const [form, setForm] = useState({ nome: "", url: "", category: "", telefone: "" });
  const [uf, setUf] = useState("BA");
  const [city, setCity] = useState<Municipality | null>(null);
  const create = useMutation({
    mutationFn: (auditar: boolean) =>
      api.post<CompanyDetail>("companies", {
        nome: form.nome,
        url: form.url,
        telefone: form.telefone,
        category: form.category ? Number(form.category) : null,
        municipality: city?.codigo_ibge ?? null,
        auditar,
      }),
    onSuccess: (c) => {
      onClose();
      const audit = c.websites[0]?.ultima_auditoria;
      navigate(audit ? `/auditorias/${audit.id}` : `/leads/${c.id}`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) {
        const cid = (e.data as { company_id?: number }).company_id;
        if (cid) navigate(`/leads/${cid}`);
      }
    },
  });
  const url = form.url && !/^https?:\/\//.test(form.url) ? `https://${form.url}` : form.url;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Cadastrar URL avulsa"
      footer={
        <>
          <Button variant="outline" disabled={!form.nome} loading={create.isPending} onClick={() => create.mutate(false)}>
            Só cadastrar
          </Button>
          <Button disabled={!form.nome || !url} loading={create.isPending} onClick={() => create.mutate(true)}>
            Cadastrar e auditar
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Nome da empresa" htmlFor="n-nome">
          <Input id="n-nome" value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} />
        </Field>
        <Field label="Site" htmlFor="n-url">
          <Input id="n-url" placeholder="exemplo.com.br" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} onBlur={() => setForm((f) => ({ ...f, url }))} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Categoria" htmlFor="n-cat">
            <Select id="n-cat" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              <option value="">—</option>
              {categories.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Telefone" htmlFor="n-tel">
            <Input id="n-tel" value={form.telefone} onChange={(e) => setForm({ ...form, telefone: e.target.value })} />
          </Field>
        </div>
        <div className="grid grid-cols-[5rem_1fr] gap-3">
          <Field label="UF" htmlFor="n-uf">
            <Select id="n-uf" value={uf} onChange={(e) => setUf(e.target.value)}>
              {UFS.map((u) => (
                <option key={u}>{u}</option>
              ))}
            </Select>
          </Field>
          <Field label="Cidade">
            <CityPicker uf={uf} value={city} onChange={setCity} />
          </Field>
        </div>
        {create.error && <p className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad">{create.error.message}</p>}
      </div>
    </Dialog>
  );
}
