export type TaskChoice = { task_id: string; title?: string; status: string };

export function selectTask<T extends TaskChoice>(tasks: T[], requestedId: string): T | null {
  // A missing/foreign requested ID must not silently select another task.
  return requestedId ? tasks.find(task => task.task_id === requestedId) ?? null : tasks.length === 1 ? tasks[0] : null;
}

export function taskHref(path: string, taskId: string): string {
  return `${path}?task=${encodeURIComponent(taskId)}`;
}

export function observationEnd(task: { attribution_window_days?: number; execution?: { started_at?: string } }): string | null {
  const started = task.execution?.started_at;
  const days = task.attribution_window_days;
  if (!started || !/(Z|[+-]\d{2}:\d{2})$/.test(started) || !Number.isInteger(days) || days! < 1 || days! > 90) return null;
  const time = Date.parse(started) + days! * 86_400_000;
  return Number.isFinite(time) ? new Date(time).toISOString() : null;
}
