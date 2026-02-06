/**
 * dataLoader.js
 * Carga los datos de las entidades desde el archivo JSON.
 * - Recupera tsne_data.json que contiene coordenadas t-SNE, entidades y contexto
 */

export async function loadTSNEData(url) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error("No se pudo cargar tsne_data.json");
  }

  return await response.json();
}
