const articleViewCache = new Map();
const articleRelationsCache = new Map();
const workspaceAggregateCache = new Map();
const workspaceRelationsCache = new Map();

function makeArticleKey(articleId, modelKey) {
  return `${String(articleId || "")}::${String(modelKey || "")}`;
}

function makeWorkspaceKey(workspaceId, modelKey) {
  return `${String(workspaceId || "")}::${String(modelKey || "")}`;
}

export function getCachedArticleView(articleId, modelKey) {
  return articleViewCache.get(makeArticleKey(articleId, modelKey)) || null;
}

export function setCachedArticleView(articleId, modelKey, payload) {
  articleViewCache.set(makeArticleKey(articleId, modelKey), payload);
}

export function getCachedArticleRelations(articleId, modelKey) {
  return articleRelationsCache.get(makeArticleKey(articleId, modelKey)) || null;
}

export function setCachedArticleRelations(articleId, modelKey, payload) {
  articleRelationsCache.set(makeArticleKey(articleId, modelKey), payload);
}

export function invalidateArticleView(articleId = "", modelKey = "") {
  if (articleId && modelKey) {
    const key = makeArticleKey(articleId, modelKey);
    articleViewCache.delete(key);
    articleRelationsCache.delete(key);
    return;
  }
  if (articleId) {
    const prefix = `${String(articleId)}::`;
    for (const key of Array.from(articleViewCache.keys())) {
      if (key.startsWith(prefix)) {
        articleViewCache.delete(key);
      }
    }
    for (const key of Array.from(articleRelationsCache.keys())) {
      if (key.startsWith(prefix)) {
        articleRelationsCache.delete(key);
      }
    }
    return;
  }
  articleViewCache.clear();
  articleRelationsCache.clear();
}

export function getCachedWorkspaceAggregate(workspaceId, modelKey) {
  return workspaceAggregateCache.get(makeWorkspaceKey(workspaceId, modelKey)) || null;
}

export function setCachedWorkspaceAggregate(workspaceId, modelKey, payload) {
  workspaceAggregateCache.set(makeWorkspaceKey(workspaceId, modelKey), payload);
}

export function getCachedWorkspaceRelations(workspaceId, modelKey) {
  return workspaceRelationsCache.get(makeWorkspaceKey(workspaceId, modelKey)) || null;
}

export function setCachedWorkspaceRelations(workspaceId, modelKey, payload) {
  workspaceRelationsCache.set(makeWorkspaceKey(workspaceId, modelKey), payload);
}

export function invalidateWorkspaceView(workspaceId = "", modelKey = "") {
  if (workspaceId && modelKey) {
    const key = makeWorkspaceKey(workspaceId, modelKey);
    workspaceAggregateCache.delete(key);
    workspaceRelationsCache.delete(key);
    return;
  }

  if (workspaceId) {
    for (const key of Array.from(workspaceAggregateCache.keys())) {
      if (key.startsWith(`${String(workspaceId)}::`)) {
        workspaceAggregateCache.delete(key);
      }
    }
    for (const key of Array.from(workspaceRelationsCache.keys())) {
      if (key.startsWith(`${String(workspaceId)}::`)) {
        workspaceRelationsCache.delete(key);
      }
    }
    return;
  }

  workspaceAggregateCache.clear();
  workspaceRelationsCache.clear();
}
