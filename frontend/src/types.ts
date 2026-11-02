// Formats échangés avec l'API (src/api/schemas.py).

export type DasType = "passif" | "actif" | "hybride";
export type Unit = "u" | "m";

export interface ModelInfo {
  version: string;
  etudes_train: number;
  surface_utilisee: boolean;
  etudes_par_das: Record<string, number>;
}

export interface Options {
  bandes: string[];
  operateurs: string[];
  familles: string[];
  types_das: DasType[];
  modele: ModelInfo | null;
}

export interface EstimateRequest {
  bandes: string[];
  operateurs: string[];
  mimo: boolean;
  etages: number;
  locaux_techniques: number;
  niveau_local: number;
  hauteur_antennes: number;
  methode: "VPLE" | "FRT";
  surface: number | null;
}

export interface EstimateLine {
  cle: string;
  libelle: string;
  unite: Unit;
  valeurs: Record<string, number>;
}

export interface EstimateResponse {
  modele: string;
  etudes_train: number;
  surface_utilisee: boolean;
  etudes_par_das: Record<string, number>;
  lignes: EstimateLine[];
  alertes: string[];
}

export interface Equipment {
  id: number;
  famille: string;
  fabricant: string;
  reference: string;
  description: string;
  unite: Unit;
  source: "saisie" | "ELR";
}

export type EquipmentInput = Omit<Equipment, "id">;

export interface ImportResult {
  trouvees: number;
  ajoutees: number;
  erreurs: string[];
}