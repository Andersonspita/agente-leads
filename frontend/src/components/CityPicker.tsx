import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";

import { api, qs } from "@/api/client";
import type { Municipality } from "@/api/types";
import { Input } from "@/components/ui";
import { cn } from "@/lib/utils";

/** Autocomplete de cidade validado contra a tabela do IBGE (RF02). */
export function CityPicker({ uf, value, onChange }: { uf: string; value: Municipality | null; onChange: (m: Municipality | null) => void }) {
  const [text, setText] = useState(value ? value.nome : "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [debounced, setDebounced] = useState(text);
  const listId = useId();

  useEffect(() => {
    const t = setTimeout(() => setDebounced(text), 200);
    return () => clearTimeout(t);
  }, [text]);

  useEffect(() => {
    if (value && value.uf !== uf && uf) {
      onChange(null);
      setText("");
    }
  }, [uf]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data = [] } = useQuery({
    queryKey: ["municipalities", uf, debounced],
    queryFn: () => api.get<Municipality[]>(`municipalities${qs({ q: debounced, uf })}`),
    enabled: open && debounced.length >= 2,
  });

  function pick(m: Municipality) {
    onChange(m);
    setText(m.nome);
    setOpen(false);
  }

  return (
    <div className="relative">
      <Input
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        placeholder={uf ? `Cidade em ${uf}…` : "Digite a cidade…"}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          setActive(0);
          if (value) onChange(null);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, data.length - 1));
          else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
          else if (e.key === "Enter" && open && data[active]) {
            e.preventDefault();
            pick(data[active]);
          }
        }}
      />
      {open && data.length > 0 && (
        <ul id={listId} role="listbox" className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border border-border bg-surface py-1 shadow-lg">
          {data.map((m, i) => (
            <li
              key={m.codigo_ibge}
              role="option"
              aria-selected={i === active}
              onMouseDown={() => pick(m)}
              className={cn("flex cursor-pointer justify-between px-3 py-1.5 text-sm", i === active && "bg-surface-2")}
            >
              <span>{m.nome}</span>
              <span className="text-xs text-muted">
                {m.uf} · IBGE {m.codigo_ibge}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
