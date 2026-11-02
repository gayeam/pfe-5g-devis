// Appels à l'API FastAPI. En développement, Vite redirige /api vers http://127.0.0.1:8000.
import type {
  Equipment,
  EquipmentInput,
  EstimateRequest,
  EstimateResponse,
  ImportResult,
  Options,
} from "./types";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

// Message lisible à partir d'une erreur FastAPI (texte ou liste de champs invalides).
function errorMessage(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "";
        return field ? `${field} : ${d.msg}` : d.msg ?? "";
      })
      .join(" ; ");
  }
  return `Erreur ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("Le serveur ne répond pas. Lancer : uvicorn src.api.main:app --reload", 0);
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(errorMessage(body.detail, response.status), response.status);
  return body as T;
}

export const api = {
  options: () => request<Options>("/api/options"),

  estimate: (input: EstimateRequest, signal?: AbortSignal) =>
    request<EstimateResponse>("/api/estimate", {
      method: "POST",
      body: JSON.stringify(input),
      signal,
    }),

  listCatalogue: (filters: { famille?: string; q?: string }, signal?: AbortSignal) => {
    const params = new URLSearchParams();
    if (filters.famille) params.set("famille", filters.famille);
    if (filters.q) params.set("q", filters.q);
    const query = params.toString();
    return request<Equipment[]>(`/api/catalogue${query ? `?${query}` : ""}`, { signal });
  },

  createEquipment: (item: EquipmentInput) =>
    request<Equipment>("/api/catalogue", { method: "POST", body: JSON.stringify(item) }),

  updateEquipment: (id: number, item: EquipmentInput) =>
    request<Equipment>(`/api/catalogue/${id}`, { method: "PUT", body: JSON.stringify(item) }),

  deleteEquipment: (id: number) => request<void>(`/api/catalogue/${id}`, { method: "DELETE" }),

  importFromElr: () => request<ImportResult>("/api/catalogue/import-elr", { method: "POST" }),
};