import type { DasType, Unit } from "./types";

const integer = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });

export function formatQuantity(value: number, unit: Unit): string {
  const shown = integer.format(Math.round(value));
  return unit === "m" ? `${shown} m` : shown;
}

export const DAS_LABELS: Record<DasType, string> = {
  passif: "DAS passif",
  actif: "DAS actif",
  hybride: "DAS hybride",
};

// Niveau du local technique : libellé affiché -> valeur envoyée à l'API.
export const LEVELS: { label: string; value: number }[] = [
  { label: "Sous-sol -3", value: -3 },
  { label: "Sous-sol -2", value: -2 },
  { label: "Sous-sol -1", value: -1 },
  { label: "RDC", value: 0 },
  ...Array.from({ length: 20 }, (_, i) => ({ label: `R+${i + 1}`, value: i + 1 })),
];

// Téléchargement d'un CSV (séparateur « ; », accents lisibles dans Excel).
export function downloadCsv(filename: string, rows: (string | number)[][]): void {
  const text = rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(";")).join("\r\n");
  const blob = new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}