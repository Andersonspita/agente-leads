import { useSearchParams } from "react-router-dom";

import { Input, Select } from "@/components/ui";
import { LEAD_STATUS } from "@/lib/labels";

export const FILTER_KEYS = ["q", "site", "bairro", "status", "nota_max", "nota_google_min", "page"] as const;

/** Filtros guardados na URL (dá para compartilhar/voltar sem perder o recorte). */
export function useFilters() {
  const [params, setParams] = useSearchParams();
  const values = Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) ?? ""])) as Record<(typeof FILTER_KEYS)[number], string>;
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  };
  return { values, set, page: Number(values.page || 1) };
}

export function CompanyFilters({ values, set }: ReturnType<typeof useFilters>) {
  return (
    <div className="flex flex-wrap items-end gap-2 border-b border-border p-3">
      <Input aria-label="Buscar por nome, domínio ou telefone" placeholder="Nome, domínio ou telefone" className="w-56" defaultValue={values.q} onKeyDown={(e) => e.key === "Enter" && set("q", e.currentTarget.value)} onBlur={(e) => set("q", e.target.value)} />
      <Select aria-label="Situação do site" className="w-40" value={values.site} onChange={(e) => set("site", e.target.value)}>
        <option value="">Todos os sites</option>
        <option value="tem_site">Tem site</option>
        <option value="sem_site">Sem site</option>
        <option value="fora_do_ar">Site fora do ar</option>
      </Select>
      <Select aria-label="Status do lead" className="w-44" value={values.status} onChange={(e) => set("status", e.target.value)}>
        <option value="">Todos os status</option>
        {Object.entries(LEAD_STATUS).map(([k, v]) => (
          <option key={k} value={k}>
            {v.nome}
          </option>
        ))}
      </Select>
      <Select aria-label="Nota do site" className="w-44" value={values.nota_max} onChange={(e) => set("nota_max", e.target.value)}>
        <option value="">Qualquer nota do site</option>
        <option value="49">Nota do site até 49</option>
        <option value="69">Nota do site até 69</option>
        <option value="84">Nota do site até 84</option>
      </Select>
      <Select aria-label="Nota no Google" className="w-40" value={values.nota_google_min} onChange={(e) => set("nota_google_min", e.target.value)}>
        <option value="">Qualquer nota Google</option>
        <option value="4">Google ≥ 4,0</option>
        <option value="4.5">Google ≥ 4,5</option>
      </Select>
      <Input aria-label="Bairro" placeholder="Bairro" className="w-36" defaultValue={values.bairro} onKeyDown={(e) => e.key === "Enter" && set("bairro", e.currentTarget.value)} onBlur={(e) => set("bairro", e.target.value)} />
    </div>
  );
}
