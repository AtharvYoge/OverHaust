// IndexedDB wrapper for the local Context Cache mirror.
// Uses the `idb` package. Stores the latest cache document per project locally.

import { openDB } from 'idb';

const DB_NAME = 'overhaust-context-runtime';
const DB_VERSION = 1;

async function getDB() {
  return openDB(DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains('caches')) {
        const s = db.createObjectStore('caches', { keyPath: 'project_id' });
        s.createIndex('user', 'user_id');
      }
      if (!db.objectStoreNames.contains('tasks')) {
        db.createObjectStore('tasks', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('meta')) {
        db.createObjectStore('meta', { keyPath: 'key' });
      }
    },
  });
}

export async function saveCacheLocal(cacheDoc) {
  if (!cacheDoc?.project_id) return;
  const db = await getDB();
  await db.put('caches', { ...cacheDoc, stored_at: new Date().toISOString() });
}

export async function loadCacheLocal(projectId) {
  const db = await getDB();
  return db.get('caches', projectId);
}

export async function saveTaskLocal(taskRun) {
  if (!taskRun?.id) return;
  const db = await getDB();
  await db.put('tasks', { ...taskRun, stored_at: new Date().toISOString() });
}

export async function loadTasksLocal(projectId) {
  const db = await getDB();
  const all = await db.getAll('tasks');
  return all.filter((t) => t.project_id === projectId).sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
}

export async function clearAllLocal() {
  const db = await getDB();
  await db.clear('caches');
  await db.clear('tasks');
  await db.clear('meta');
}

export async function getLocalStats() {
  const db = await getDB();
  const caches = await db.getAll('caches');
  const tasks = await db.getAll('tasks');
  const items = caches.reduce((acc, c) => acc + (c.metrics?.knowledge_items || 0), 0);
  let last = null;
  for (const c of caches) {
    if (!last || (c.stored_at || '') > last) last = c.stored_at || last;
  }
  for (const t of tasks) {
    if (!last || (t.stored_at || '') > last) last = t.stored_at || last;
  }
  const rough = JSON.stringify(caches).length + JSON.stringify(tasks).length;
  return {
    projects_with_cache: caches.length,
    task_runs: tasks.length,
    knowledge_items: items,
    approx_size_bytes: rough,
    last_updated: last,
  };
}
