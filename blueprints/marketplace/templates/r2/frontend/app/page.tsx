import { publicListings } from '@/lib/api';

export const dynamic = 'force-dynamic';
export default async function HomePage() {
  let listings;
  try { listings = await publicListings(); }
  catch { return <section><h1>Каталог временно недоступен</h1><p>Проверьте локальный API.</p></section>; }
  return (
    <section>
      <h1>Каталог товаров</h1>
      <p>Только опубликованные товары с подтверждённой ревизией.</p>
      {listings.length === 0 ? <p>Пока нет опубликованных товаров.</p> :
        <div className="cards">{listings.map(x => <article key={x.id}>
          <h2>{x.title}</h2><p>{x.description}</p><strong>{x.price} {x.currency}</strong>
        </article>)}</div>}
    </section>
  );
}
