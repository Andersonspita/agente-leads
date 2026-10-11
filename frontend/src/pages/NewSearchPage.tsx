import { useMutation, useQuery } from "@tanstack/react-query";
import { Search as SearchIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import type { Capabilities, Category, Municipality, Search } from "@/api/types";
import { CityPicker } from "@/components/CityPicker";
import { PageBody, PageHeader } from "@/components/Layout";
import { Button, Card, Field, Input, Select } from "@/components/ui";
import { UFS } from "@/lib/labels";

export default function NewSearchPage() {
  const navigate = useNavigate();
  const categories = useQuery({ queryKey: ["categories", "ativas"], queryFn: () => api.get<Category[]>("categories?ativas=1") });
  const caps = useQuery({ queryKey: ["capabilities"], queryFn: () => api.get<Capabilities>("settings/capabilities") });
  const [category, setCategory] = useState("");
  const [freeText, setFreeText] = useState("");
  const [uf, setUf] = useState("BA");
  const [city, setCity] = useState<Municipality | null>(null);
  const [bairro, setBairro] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api.post<Search>("searches", {
        category: category ? Number(category) : null,
        termo_livre: freeText.trim(),
        municipality: city!.codigo_ibge,
        bairro: bairro.trim(),
      }),
    onSuccess: (s) => navigate(`/buscas/${s.id}`),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };
  const selected = categories.data?.find((c) => String(c.id) === category);

  return (
    <>
      <PageHeader title="Nova busca" description="Encontre empresas de uma categoria numa cidade" back={<Link to="/buscas">← Buscas</Link>} />
      <PageBody>
        <Card className="max-w-2xl p-5">
          <form onSubmit={submit} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Categoria" htmlFor="cat" hint={selected ? `Termos: ${selected.termos_busca.join(", ")} · CNAE ${selected.cnaes.join(", ")}` : "Lista pré-definida"}>
                <Select id="cat" value={category} onChange={(e) => setCategory(e.target.value)}>
                  <option value="">— texto livre —</option>
                  {categories.data?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nome}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Ou termo livre" htmlFor="free" hint="Substitui os termos da categoria na busca do Google">
                <Input id="free" placeholder="ex.: clínica de estética" value={freeText} onChange={(e) => setFreeText(e.target.value)} />
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-[6rem_1fr]">
              <Field label="UF" htmlFor="uf">
                <Select id="uf" value={uf} onChange={(e) => setUf(e.target.value)}>
                  {UFS.map((u) => (
                    <option key={u}>{u}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Cidade" hint={city ? `Código IBGE ${city.codigo_ibge}` : "Escolha na lista (validada pelo IBGE)"}>
                <CityPicker uf={uf} value={city} onChange={setCity} />
              </Field>
            </div>
            <Field label="Bairro (opcional)" htmlFor="bairro">
              <Input id="bairro" value={bairro} onChange={(e) => setBairro(e.target.value)} />
            </Field>

            {caps.data && (
              <p className="rounded-md bg-surface-2 px-3 py-2 text-xs text-muted">
                Fontes desta busca:{" "}
                {[
                  caps.data.google_places && "Google Places",
                  caps.data.osm && "OpenStreetMap",
                  "base CNPJ" + (caps.data.base_cnpj ? "" : " (ainda vazia — rode import_cnpj)"),
                  caps.data.email_cnpj && "site pelo e-mail do CNPJ",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            )}
            {create.error && <p className="rounded-md bg-bad-soft px-3 py-2 text-sm text-bad">{create.error.message}</p>}
            <div className="flex justify-end">
              <Button type="submit" disabled={!city || (!category && !freeText.trim())} loading={create.isPending}>
                <SearchIcon className="size-4" aria-hidden /> Buscar empresas
              </Button>
            </div>
          </form>
        </Card>
      </PageBody>
    </>
  );
}
