'use client';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import type { Listing } from '@/lib/api';
import { getJson, getSession, postJson, type SessionInfo } from '@/lib/session';

export default function ModerationPage() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [items, setItems] = useState<Listing[]>([]);
  const [loginForm, setLoginForm] = useState({username:'',password:''});
  const [reasons, setReasons] = useState<Record<string,string>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const refresh = useCallback(async () => {
    const user=await getSession(); setSession(user);
    setItems(user.authenticated && user.moderator ? await getJson<Listing[]>('/api/moderation/queue/') : []);
  },[]);
  useEffect(()=>{void refresh().catch(e=>setMessage(String(e)));},[refresh]);
  async function login(event:FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setMessage('');
    try{await postJson('/api/auth/login/',loginForm);await refresh();setLoginForm({username:'',password:''});}
    catch(e){setMessage(String(e));}finally{setBusy(false);}}
  async function logout(){setBusy(true);try{await postJson('/api/auth/logout/',{});await refresh();}
    catch(e){setMessage(String(e));}finally{setBusy(false);}}
  async function decide(item:Listing,verdict:'APPROVE'|'REJECT'){
    setBusy(true);setMessage('');
    try{
      await postJson(`/api/moderation/${item.id}/decision/`,{
        decision_id:crypto.randomUUID(),expected_revision:item.content_revision,
        verdict,reason:reasons[item.id]||'',
      });
      await refresh();setMessage(`Решение ${verdict} сохранено для ревизии ${item.content_revision}.`);
    }catch(e){setMessage(String(e));}finally{setBusy(false);}
  }
  return <section className="workspace"><h1>Очередь модерации</h1>
    <p>Решение принимает человек с назначенными администратором статусом staff и группой moderator.</p>
    {message&&<p role="status" className="message">{message}</p>}
    {!session?<p>Подключаемся к API...</p>:!session.authenticated?<form className="panel" onSubmit={login}>
      <label>Пользователь <input required autoComplete="username" value={loginForm.username} onChange={e=>setLoginForm({...loginForm,username:e.target.value})}/></label>
      <label>Пароль <input required type="password" autoComplete="current-password" value={loginForm.password} onChange={e=>setLoginForm({...loginForm,password:e.target.value})}/></label>
      <button disabled={busy}>Войти</button>
    </form>:!session.moderator?<div className="panel"><p>Доступ только для moderator/staff.</p><button onClick={logout} disabled={busy}>Выйти</button></div>:<>
      <div className="toolbar">Модератор: {session.username}<button disabled={busy} onClick={logout}>Выйти</button></div>
      {items.length===0?<p>Очередь пуста.</p>:<div className="cards">{items.map(item=><article key={item.id}>
        <h2>{item.title}</h2><p>{item.description}</p><p>{item.price} {item.currency}</p>
        <p>Ревизия: {item.content_revision}</p>
        <label>Причина решения <textarea maxLength={300} value={reasons[item.id]||''} onChange={e=>setReasons({...reasons,[item.id]:e.target.value})}/></label>
        <div className="actions"><button disabled={busy} onClick={()=>void decide(item,'APPROVE')}>Одобрить</button>
          <button disabled={busy} className="danger" onClick={()=>void decide(item,'REJECT')}>Отклонить</button></div>
      </article>)}</div>}
    </>}
  </section>;
}
