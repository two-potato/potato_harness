/** Browser-only JSON session client. Django grants all authority, never this UI. */
export type SessionInfo = {authenticated: boolean; username: string; seller: boolean; moderator: boolean};

export async function getSession(): Promise<SessionInfo> {
  const response = await fetch('/api/auth/session/', {credentials: 'same-origin', cache: 'no-store'});
  if (!response.ok) throw new Error('Сессионный API недоступен');
  return (await response.json()) as SessionInfo;
}

function csrfToken(): string {
  const entry = document.cookie.split('; ').find(x => x.startsWith('csrftoken='));
  if (!entry) throw new Error('CSRF cookie отсутствует. Обновите страницу.');
  return decodeURIComponent(entry.substring('csrftoken='.length));
}

export async function postJson<T>(path: string, payload: unknown, method = 'POST'): Promise<T> {
  if (!path.startsWith('/api/') || path.startsWith('//')) throw new Error('Недопустимый API путь');
  const response = await fetch(path, {
    method, credentials: 'same-origin', cache: 'no-store',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`API отказал: HTTP ${response.status}`);
  return (await response.json()) as T;
}

export async function getJson<T>(path: string): Promise<T> {
  if (!path.startsWith('/api/') || path.startsWith('//')) throw new Error('Недопустимый API путь');
  const response = await fetch(path, {credentials: 'same-origin', cache: 'no-store'});
  if (!response.ok) throw new Error(`API отказал: HTTP ${response.status}`);
  return (await response.json()) as T;
}
