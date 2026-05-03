function apiRoot() {
  if (typeof document === "undefined") return "/api";
  const meta = document.querySelector('meta[name="scibert-api-root"]');
  const raw = meta && typeof meta.content === "string" ? meta.content.trim() : "";
  return raw.replace(/\/+$/, "") || "/api";
}

export async function listWorkspaces() {
  const root = apiRoot();
  const response = await fetch(`${root}/workspaces`);
  if (!response.ok) {
    throw new Error("No se pudo cargar la lista de workspaces");
  }
  return response.json();
}

export async function getWorkspace(workspaceId) {
  const root = apiRoot();
  const response = await fetch(`${root}/workspaces/${encodeURIComponent(workspaceId)}`);
  if (!response.ok) {
    throw new Error("No se pudo cargar el workspace");
  }
  return response.json();
}

export async function createWorkspace(payload) {
  const root = apiRoot();
  const response = await fetch(`${root}/workspaces`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "No se pudo crear el workspace");
  }
  return result;
}

export async function updateWorkspace(workspaceId, payload) {
  const root = apiRoot();
  const response = await fetch(`${root}/workspaces/${encodeURIComponent(workspaceId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "No se pudo actualizar el workspace");
  }
  return result;
}

export async function deleteWorkspace(workspaceId) {
  const root = apiRoot();
  const response = await fetch(`${root}/workspaces/${encodeURIComponent(workspaceId)}`, {
    method: "DELETE",
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "No se pudo eliminar el workspace");
  }
  return result;
}

export async function updateWorkspaceArticles(workspaceId, articleIds, mode = "add") {
  const root = apiRoot();
  const response = await fetch(`${root}/workspaces/${encodeURIComponent(workspaceId)}/articles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      article_ids: Array.isArray(articleIds) ? articleIds : [],
      mode,
    }),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "No se pudo actualizar el workspace");
  }
  return result;
}

export async function processWorkspace(workspaceId, modelKey) {
  const root = apiRoot();
  const response = await fetch(`${root}/workspaces/${encodeURIComponent(workspaceId)}/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: modelKey }),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "No se pudo procesar el workspace");
  }
  return result;
}
