import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { DAS_LABELS, LEVELS, downloadCsv, formatQuantity } from "../format";
import type { DasType, EstimateRequest, EstimateResponse, Options } from "../types";
import ChipSelect from "./ChipSelect";

const DEFAULT_FORM: EstimateRequest = {
  bandes: ["1800 MHz (4G)", "2100 MHz (4G)"],
  operateurs: ["BOUYGUES"],
  mimo: false,
  etages: 3,
  locaux_techniques: 1,
  niveau_local: 0,
  hauteur_antennes: 2.5,
  methode: "VPLE",
  surface: null,
};

export default function EstimationPage({ options }: { options: Options }) {
  const [form, setForm] = useState<EstimateRequest>(DEFAULT_FORM);
  const [result, setResult] = useState<EstimateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const surfaceUsed = options.modele?.surface_utilisee ?? false;

  const update = <K extends keyof EstimateRequest>(key: K, value: EstimateRequest[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  // Recalcul à chaque modification (petit délai pour ne pas appeler l'API à chaque frappe).
  useEffect(() => {
    if (!options.modele) return;
    if (form.bandes.length === 0 || form.operateurs.length === 0) {
      setResult(null);
      setError("Choisir au moins une bande et un opérateur.");
      return;
    }
    if (surfaceUsed && !form.surface) {
      setResult(null);
      setError("Renseigner la surface prédite : le modèle l'utilise.");
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      api
        .estimate({ ...form, surface: surfaceUsed ? form.surface : null }, controller.signal)
        .then((r) => {
          setResult(r);
          setError(null);
        })
        .catch((e: ApiError) => {
          if (e.name !== "AbortError") setError(e.message);
        })
        .finally(() => setLoading(false));
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [form, options.modele, surfaceUsed]);

  const das = options.types_das;

  const exportCsv = () => {
    if (!result) return;
    downloadCsv("estimation_das.csv", [
      ["Quantité", "Unité", ...das.map((d) => DAS_LABELS[d])],
      ...result.lignes.map((l) => [l.libelle, l.unite, ...das.map((d) => Math.round(l.valeurs[d]))]),
    ]);
  };

  return (
    <div className="layout">
      <section className="card form-card" aria-label="Entrées de l'étude">
        <h2>Étude</h2>
        <ChipSelect label="Bandes" options={options.bandes} selected={form.bandes} onChange={(v) => update("bandes", v)} />
        <ChipSelect label="Opérateurs" options={options.operateurs} selected={form.operateurs} onChange={(v) => update("operateurs", v)} />

        <label className="switch">
          <input type="checkbox" checked={form.mimo} onChange={(e) => update("mimo", e.target.checked)} />
          <span className="switch-track" aria-hidden />
          MIMO sur au moins une bande
        </label>

        <div className="row">
          <label className="field">
            <span>Étages</span>
            <input type="number" min={1} max={200} value={form.etages} onChange={(e) => update("etages", Math.max(1, Number(e.target.value) || 1))} />
          </label>
          <label className="field">
            <span>Locaux techniques</span>
            <input type="number" min={1} max={50} value={form.locaux_techniques} onChange={(e) => update("locaux_techniques", Math.max(1, Number(e.target.value) || 1))} />
          </label>
        </div>

        <div className="row">
          <label className="field">
            <span>Niveau du local technique</span>
            <select value={form.niveau_local} onChange={(e) => update("niveau_local", Number(e.target.value))}>
              {LEVELS.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Hauteur des antennes (m)</span>
            <input type="number" min={0.5} max={50} step={0.1} value={form.hauteur_antennes} onChange={(e) => update("hauteur_antennes", Number(e.target.value) || 2.5)} />
          </label>
        </div>

        <div className="field">
          <span>Méthode</span>
          <div className="segmented" role="radiogroup">
            {(["VPLE", "FRT"] as const).map((m) => (
              <button type="button" key={m} role="radio" aria-checked={form.methode === m} className={form.methode === m ? "on" : ""} onClick={() => update("methode", m)}>
                {m}
              </button>
            ))}
          </div>
        </div>

        <label className="field">
          <span>
            Surface prédite (m²) {!surfaceUsed && <span className="muted small">— pas encore utilisée par le modèle</span>}
          </span>
          <input
            type="number"
            min={0}
            step={100}
            disabled={!surfaceUsed}
            value={form.surface ?? ""}
            placeholder={surfaceUsed ? "ex. 12000" : "disponible quand les surfaces seront saisies"}
            onChange={(e) => update("surface", e.target.value === "" ? null : Number(e.target.value))}
          />
        </label>

        <button type="button" className="btn btn-ghost" onClick={() => setForm(DEFAULT_FORM)}>
          Réinitialiser
        </button>
      </section>

      <section className="results" aria-live="polite" aria-label="Estimation">
        {!options.modele && (
          <div className="card empty">
            <h2>Aucun modèle entraîné</h2>
            <p className="muted">
              Lancer <code>python -m src.model.train --root data</code>, puis recharger la page.
            </p>
          </div>
        )}

        {options.modele && (
          <>
            <div className="results-head">
              <h2>Estimation par type de DAS {loading && <span className="spinner" aria-label="Calcul en cours" />}</h2>
              <button type="button" className="btn btn-small" onClick={exportCsv} disabled={!result}>
                Exporter (CSV)
              </button>
            </div>

            {error && <div className="alert alert-warn">{error}</div>}

            {result && (
              <>
                <div className="kpis">
                  {das.map((d: DasType) => {
                    const antennas = result.lignes.find((l) => l.cle === "design_elements");
                    const n = result.etudes_par_das[d] ?? 0;
                    return (
                      <div key={d} className={`card kpi kpi-${d}`}>
                        <span className="kpi-label">{DAS_LABELS[d]}</span>
                        <span className="kpi-value">{antennas ? formatQuantity(antennas.valeurs[d], "u") : "–"}</span>
                        <span className="kpi-sub">antennes · {n} étude{n > 1 ? "s" : ""} de référence</span>
                      </div>
                    );
                  })}
                </div>

                <div className="card table-card">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Quantité</th>
                        {das.map((d) => (
                          <th key={d} className="num">
                            {DAS_LABELS[d]}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.lignes
                        .filter((l) => l.cle !== "design_elements")
                        .map((l) => (
                          <tr key={l.cle}>
                            <td>{l.libelle}</td>
                            {das.map((d) => (
                              <td key={d} className={l.valeurs[d] < 0.5 ? "num zero" : "num"}>
                                {formatQuantity(l.valeurs[d], l.unite)}
                              </td>
                            ))}
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>

                {result.alertes.map((a) => (
                  <div key={a} className="alert alert-warn">
                    {a}
                  </div>
                ))}
                <p className="muted small">
                  Modèle {result.modele}, entraîné sur {result.etudes_train} études
                  {result.surface_utilisee ? "" : ", sans la surface"}. Estimation indicative, pas un relevé de conception.
                </p>
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}