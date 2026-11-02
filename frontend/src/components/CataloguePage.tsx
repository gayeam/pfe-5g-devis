import { useCallback, useEffect, useState } from "react";
import type { KeyboardEvent } from "react";
import { api, ApiError } from "../api";
import type { Equipment, EquipmentInput } from "../types";

const EMPTY: EquipmentInput = {
  famille: "",
  fabricant: "",
  reference: "",
  description: "",
  unite: "u",
  source: "saisie",
};

type Notice = { kind: "ok" | "error"; text: string } | null;

export default function CataloguePage({ families }: { families: string[] }) {
  const [items, setItems] = useState<Equipment[]>([]);
  const [query, setQuery] = useState("");
  const [family, setFamily] = useState("");
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<Notice>(null);
  const [adding, setAdding] = useState<EquipmentInput | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<EquipmentInput>(EMPTY);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [importing, setImporting] = useState(false);

  const reload = useCallback(
    (signal?: AbortSignal) => {
      setLoading(true);
      return api
        .listCatalogue({ q: query.trim(), famille: family }, signal)
        .then(setItems)
        .catch((e: ApiError) => {
          if (e.name !== "AbortError") setNotice({ kind: "error", text: e.message });
        })
        .finally(() => setLoading(false));
    },
    [query, family],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => reload(controller.signal), 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [reload]);

  const fail = (e: ApiError) => setNotice({ kind: "error", text: e.message });

  const saveNew = () => {
    if (!adding) return;
    api
      .createEquipment(adding)
      .then((item) => {
        setAdding(null);
        setNotice({ kind: "ok", text: `Référence ${item.reference} ajoutée.` });
        reload();
      })
      .catch(fail);
  };

  const startEdit = (item: Equipment) => {
    const { id, ...rest } = item;
    setEditingId(id);
    setDraft(rest);
    setConfirmId(null);
  };

  const saveEdit = () => {
    if (editingId === null) return;
    api
      .updateEquipment(editingId, draft)
      .then((item) => {
        setEditingId(null);
        setNotice({ kind: "ok", text: `Référence ${item.reference} modifiée.` });
        reload();
      })
      .catch(fail);
  };

  const remove = (item: Equipment) => {
    api
      .deleteEquipment(item.id)
      .then(() => {
        setConfirmId(null);
        setNotice({ kind: "ok", text: `Référence ${item.reference} supprimée.` });
        reload();
      })
      .catch(fail);
  };

  const importElr = () => {
    setImporting(true);
    api
      .importFromElr()
      .then((r) => {
        const errors = r.erreurs.length ? ` ${r.erreurs.length} ELR illisible(s).` : "";
        setNotice({ kind: "ok", text: `${r.ajoutees} référence(s) ajoutée(s) sur ${r.trouvees} trouvée(s) dans les ELR.${errors}` });
        reload();
      })
      .catch(fail)
      .finally(() => setImporting(false));
  };

  return (
    <section className="card catalogue">
      <div className="results-head">
        <div>
          <h2>Catalogue constructeurs</h2>
          <p className="muted small">Références de matériel par famille. Les prix et fournisseurs viendront avec le chiffrage.</p>
        </div>
        <div className="actions">
          <button type="button" className="btn" onClick={importElr} disabled={importing}>
            {importing ? "Import en cours…" : "Importer depuis les ELR"}
          </button>
          <button type="button" className="btn btn-primary" onClick={() => { setAdding({ ...EMPTY }); setEditingId(null); }} disabled={adding !== null}>
            Ajouter une référence
          </button>
        </div>
      </div>

      <div className="toolbar">
        <input type="search" placeholder="Rechercher (fabricant, référence, description)" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Rechercher" />
        <select value={family} onChange={(e) => setFamily(e.target.value)} aria-label="Filtrer par famille">
          <option value="">Toutes les familles</option>
          {families.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
        <span className="muted small">{loading ? "Chargement…" : `${items.length} référence${items.length > 1 ? "s" : ""}`}</span>
      </div>

      {notice && (
        <div className={notice.kind === "ok" ? "alert alert-ok" : "alert alert-error"}>
          {notice.text}
          <button type="button" className="btn btn-small btn-ghost" onClick={() => setNotice(null)} aria-label="Fermer">
            ×
          </button>
        </div>
      )}

      <div className="table-scroll">
        <table className="table catalogue-table">
          <thead>
            <tr>
              <th>Famille</th>
              <th>Fabricant</th>
              <th>Référence</th>
              <th>Description</th>
              <th>Unité</th>
              <th>Source</th>
              <th className="actions-col" aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {adding && (
              <EditRow value={adding} families={families} onChange={setAdding} onSave={saveNew} onCancel={() => setAdding(null)} highlight />
            )}
            {items.map((item) =>
              editingId === item.id ? (
                <EditRow key={item.id} value={draft} families={families} onChange={setDraft} onSave={saveEdit} onCancel={() => setEditingId(null)} />
              ) : (
                <tr key={item.id}>
                  <td>{item.famille || <span className="muted">—</span>}</td>
                  <td>{item.fabricant}</td>
                  <td className="mono">{item.reference}</td>
                  <td className="desc" title={item.description}>
                    {item.description}
                  </td>
                  <td>{item.unite}</td>
                  <td>
                    <span className={item.source === "ELR" ? "tag tag-elr" : "tag"}>{item.source}</span>
                  </td>
                  <td className="actions-col">
                    {confirmId === item.id ? (
                      <>
                        <button type="button" className="btn btn-small btn-danger" onClick={() => remove(item)}>
                          Confirmer
                        </button>
                        <button type="button" className="btn btn-small btn-ghost" onClick={() => setConfirmId(null)}>
                          Annuler
                        </button>
                      </>
                    ) : (
                      <>
                        <button type="button" className="btn btn-small btn-ghost" onClick={() => startEdit(item)}>
                          Modifier
                        </button>
                        <button type="button" className="btn btn-small btn-ghost danger-text" onClick={() => setConfirmId(item.id)}>
                          Supprimer
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ),
            )}
            {!loading && items.length === 0 && !adding && (
              <tr>
                <td colSpan={7} className="empty-row">
                  {query || family
                    ? "Aucune référence ne correspond à ce filtre."
                    : "Catalogue vide. Ajoutez une référence, ou importez celles des ELR de vos études."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

interface EditRowProps {
  value: EquipmentInput;
  families: string[];
  onChange: (value: EquipmentInput) => void;
  onSave: () => void;
  onCancel: () => void;
  highlight?: boolean;
}

function EditRow({ value, families, onChange, onSave, onCancel, highlight }: EditRowProps) {
  const set = <K extends keyof EquipmentInput>(key: K, v: EquipmentInput[K]) => onChange({ ...value, [key]: v });
  const onKey = (e: KeyboardEvent<HTMLTableRowElement>) => {
    if (e.key === "Enter") onSave();
    if (e.key === "Escape") onCancel();
  };
  return (
    <tr className={highlight ? "edit-row new" : "edit-row"} onKeyDown={onKey}>
      <td>
        <select value={value.famille} onChange={(e) => set("famille", e.target.value)} aria-label="Famille">
          <option value="">—</option>
          {families.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </td>
      <td>
        <input value={value.fabricant} onChange={(e) => set("fabricant", e.target.value)} aria-label="Fabricant" placeholder="Fabricant" />
      </td>
      <td>
        <input value={value.reference} onChange={(e) => set("reference", e.target.value)} aria-label="Référence" placeholder="Référence *" autoFocus />
      </td>
      <td>
        <input value={value.description} onChange={(e) => set("description", e.target.value)} aria-label="Description" placeholder="Description" />
      </td>
      <td>
        <select value={value.unite} onChange={(e) => set("unite", e.target.value as EquipmentInput["unite"])} aria-label="Unité">
          <option value="u">u</option>
          <option value="m">m</option>
        </select>
      </td>
      <td>
        <span className="tag">{value.source}</span>
      </td>
      <td className="actions-col">
        <button type="button" className="btn btn-small btn-primary" onClick={onSave} disabled={!value.reference.trim()}>
          Enregistrer
        </button>
        <button type="button" className="btn btn-small btn-ghost" onClick={onCancel}>
          Annuler
        </button>
      </td>
    </tr>
  );
}