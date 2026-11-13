'use client';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import type { Listing } from '@/lib/api';
import { getJson, getSession, postJson, type SessionInfo } from '@/lib/session';

type Credential = {username: string; password: string};
type ListingInput = {slug: string; title: string; description: string; price: string; currency: string};
const EMPTY: ListingInput = {slug:'', title:'', description:'', price:'0.00', currency:'KZT'};

export default function SellerPage() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [credentials, setCredentials] = useState<Credential>({username:'', password:''});
  const [items, setItems] = useState<Listing[]>([]);
  const [form, setForm] = useState<ListingInput>(EMPTY);
  const [editing, setEditing] = useState<Listing | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const user = await getSession();
    setSession(user);
    setItems(user.authenticated && user.seller ? await getJson<Listing[]>('/api/me/listings/') : []);
  }, []);

  useEffect(() => { void refresh().catch(e => setMessage(String(e))); }, [refresh]);

  async function submitCredentials(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage('');
    try { await postJson('/api/auth/login/', credentials); await refresh(); setCredentials({username:'',password:''}); }
    catch(e) { setMessage(String(e)); } finally { setBusy(false); }
  }

  async function signOut() {
    setBusy(true); setMessage('');
    try { await postJson('/api/auth/logout/', {}); await refresh(); setEditing(null); }
    catch(e) { setMessage(String(e)); } finally { setBusy(false); }
  }

  async function submitItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      if (editing) {
        await postJson(`/api/listings/${editing.id}/`, {...form, expected_revision: editing.content_revision}, 'PATCH');
      } else {
        await postJson('/api/listings/', form);
      }
      setEditing(null); setForm(EMPTY); await refresh(); setMessage('Черновик сохранён.');
    } catch(e) {setMessage(String(e));} finally {setBusy(false);}
  }

  async function submitReview(item: Listing) {
    setBusy(true); setMessage('');
    try { await postJson(`/api/listings/${item.id}/submit/`, {expected_revision:item.content_revision});
      await refresh(); setMessage('Отправлено на проверку модератору.'); }
    catch(e) {setMessage(String(e));} finally {setBusy(false);}
  }

  return <section className="workspace">
    <h1>Кабинет продавца</h1><p>Локальная демонстрация. Роль продавца назначается администратором Django.</p>
    {message && <p role="status" className="message">{message}</p>}
    {!session ? <p>Подключаемся к API...</p> : !session.authenticated ?
      <form onSubmit={submitCredentials} className="panel">
        <h2>Вход в аккаунт</h2>
        <label>Пользователь <input autoComplete="username" required maxLength={150} value={credentials.username} onChange={e=>setCredentials({...credentials,username:e.target.value})}/></label>
        <label>Пароль <input type="password" autoComplete="current-password" required value={credentials.password} onChange={e=>setCredentials({...credentials,password:e.target.value})}/></label>
        <button disabled={busy}>Войти</button>
      </form> : !session.seller ? <div className="panel"><p>Роль seller не назначена. Доступ закрыт.</p><button disabled={busy} onClick={signOut}>Выйти</button></div> : <>
      <div className="toolbar"><span>Продавец: {session.username}</span><button disabled={busy} onClick={signOut}>Выйти</button></div>
      <form onSubmit={submitItem} className="panel">
        <h2>{editing ? 'Редактировать товар' : 'Новый товар'}</h2>
        <label>Код товара <input required pattern="[a-z0-9-]+" maxLength={80} disabled={!!editing} value={form.slug} onChange={e=>setForm({...form,slug:e.target.value})}/></label>
        <label>Название <input required maxLength={200} value={form.title} onChange={e=>setForm({...form,title:e.target.value})}/></label>
        <label>Описание <textarea maxLength={4096} value={form.description} onChange={e=>setForm({...form,description:e.target.value})}/></label>
        <label>Цена в KZT <input required type="number" step="0.01" min="0" value={form.price} onChange={e=>setForm({...form,price:e.target.value})}/></label>
        <button disabled={busy}>{editing ? 'Сохранить новую ревизию' : 'Создать черновик'}</button>
        {editing && <button type="button" className="secondary" onClick={()=>{setEditing(null);setForm(EMPTY);}}>Отмена</button>}
      </form>
      <h2>Мои товары</h2>
      {items.length===0 ? <p>Товаров пока нет.</p> : <div className="cards">{items.map(item=><article key={item.id}>
        <h3>{item.title}</h3><p>{item.description}</p><p>{item.price} {item.currency}</p>
        <p>Статус: <strong>{item.status}</strong> · Ревизия {item.content_revision}</p>
        <div className="actions">
          <button disabled={busy} onClick={()=>{setEditing(item);setForm({slug:item.slug,title:item.title,description:item.description,price:item.price,currency:item.currency});}}>Редактировать</button>
          {item.status==='DRAFT' && <button disabled={busy} onClick={()=>void submitReview(item)}>На модерацию</button>}
        </div>
      </article>)}</div>}
    </>}
  </section>;
}
