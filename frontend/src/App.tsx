import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import type { Options } from "./types";
import EstimationPage from "./components/EstimationPage";
import CataloguePage from "./components/CataloguePage";

type Tab = "estimation" | "catalogue";

export default function App() {
  const [tab, setTab] = useState<Tab>("estimation");
  const [options, setOptions] = useState<Options | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadOptions = () => {
    setError(null);
    api
      .options()
      .then(setOptions)
      .catch((e: ApiError) => setError(e.message));
  };

  useEffect(loadOptions, []);

  const model = options?.modele;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>
            ◎
          </span>
          <div>
            <h1>Pré-dimensionnement DAS</h1>
            <p className="muted small">Estimation du matériel à partir des études passées</p>
          </div>
        </div>
        {model ? (
          <span className="badge" title="Modèle chargé par l'API">
            Modèle {model.version} · {model.etudes_train} études
            {model.surface_utilisee ? " · avec surface" : " · sans surface"}
          </span>
        ) : options ? (
          <span className="badge badge-warn">Aucun modèle entraîné</span>
        ) : null}
      </header>

      <nav className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "estimation"} className={tab === "estimation" ? "tab active" : "tab"} onClick={() => setTab("estimation")}>
          Estimation
        </button>
        <button role="tab" aria-selected={tab === "catalogue"} className={tab === "catalogue" ? "tab active" : "tab"} onClick={() => setTab("catalogue")}>
          Catalogue constructeurs
        </button>
      </nav>

      <main>
        {error && (
          <div className="alert alert-error">
            {error}
            <button className="btn btn-small" onClick={loadOptions}>
              Réessayer
            </button>
          </div>
        )}
        {options && tab === "estimation" && <EstimationPage options={options} />}
        {options && tab === "catalogue" && <CataloguePage families={options.familles} />}
        {!options && !error && <p className="muted">Chargement…</p>}
      </main>
    </div>
  );
}