import os, re, io, json, time, sqlite3, hashlib, asyncio, html
from datetime import datetime
from urllib.parse import quote_plus, urlparse
from contextlib import suppress

import requests
from PIL import Image
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID', '@myminerals').strip()
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID', '').strip()
LOCAL_TZ = os.getenv('LOCAL_TZ', 'Europe/Moscow')
POST_TIMES = [x.strip() for x in os.getenv('POST_TIMES', '09:00,18:00').split(',') if x.strip()]
AUTO_ENABLED = os.getenv('AUTO_ENABLED', '0') == '1'

GROQ_API_KEY = os.getenv('GROQ_API_KEY', '').strip()
GROQ_BASE_URL = os.getenv('GROQ_BASE_URL', 'https://api.groq.com/openai/v1').rstrip('/')
GROQ_MODEL = os.getenv('GROQ_MODEL', 'qwen/qwen3.6-27b').strip()
MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY', '').strip()
MISTRAL_BASE_URL = os.getenv('MISTRAL_BASE_URL', 'https://api.mistral.ai/v1').rstrip('/')
MISTRAL_MODEL = os.getenv('MISTRAL_MODEL', 'mistral-small-latest').strip()
LLM_TIMEOUT = int(os.getenv('LLM_TIMEOUT', '90'))
LLM_MAX_TOKENS = int(os.getenv('LLM_MAX_TOKENS', '1800'))

GOOGLE_CSE_API_KEY = os.getenv('GOOGLE_CSE_API_KEY', '').strip()
GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID', '').strip()
GOOGLE_HTML_ENABLED = os.getenv('GOOGLE_HTML_ENABLED', '1') != '0'
WIKIMEDIA_ENABLED = os.getenv('WIKIMEDIA_ENABLED', '1') != '0'
STRICT_LICENSE = os.getenv('STRICT_LICENSE', '0') == '1'

IMAGE_MIN_WIDTH = int(os.getenv('IMAGE_MIN_WIDTH', '700'))
IMAGE_MIN_HEIGHT = int(os.getenv('IMAGE_MIN_HEIGHT', '700'))
IMAGE_MIN_BYTES = int(os.getenv('IMAGE_MIN_BYTES', '25000'))
IMAGE_MAX_BYTES = int(os.getenv('IMAGE_MAX_BYTES', str(12 * 1024 * 1024)))
IMAGE_TIMEOUT = int(os.getenv('IMAGE_TIMEOUT', '25'))
IMAGE_CANDIDATES = int(os.getenv('IMAGE_CANDIDATES', '24'))
IMAGE_DOWNLOAD_CANDIDATES = int(os.getenv('IMAGE_DOWNLOAD_CANDIDATES', '12'))

WIKIMEDIA_API = 'https://commons.wikimedia.org/w/api.php'
WIKIPEDIA_API = 'https://ru.wikipedia.org/w/api.php'
USER_AGENT = 'MyMineralsBot/2.2.6 (+https://github.com/gotock-crypto/myminerals)'

logging_config = {'level': 'INFO', 'format': '%(asctime)s %(levelname)s %(name)s: %(message)s'}
import logging
logging.basicConfig(**logging_config)
log = logging.getLogger('minerals')
for _name in ('httpx', 'httpcore', 'telegram', 'telegram.ext'):
    logging.getLogger(_name).setLevel(logging.WARNING)

MINERALS = ['Берилл','Аквамарин','Изумруд','Аметист','Топаз','Турмалин','Гранат','Малахит','Лазурит','Опал','Кварц','Розовый кварц','Цитрин','Агат','Оникс','Яшма','Обсидиан','Флюорит','Кальцит','Пирит','Гематит','Магнетит','Авантюрин','Амазонит','Лабрадорит','Родонит','Селенит','Шунгит','Кианит','Циркон','Корунд','Рубин','Сапфир','Нефрит','Жадеит','Морганит','Гелиодор','Гошенит','Апатит','Содалит','Танзанит']
MINERAL_EN = {
    'Берилл':'beryl','Аквамарин':'aquamarine','Изумруд':'emerald','Аметист':'amethyst','Топаз':'topaz','Турмалин':'tourmaline','Гранат':'garnet','Малахит':'malachite','Лазурит':'lapis lazuli','Опал':'opal','Кварц':'quartz','Розовый кварц':'rose quartz','Цитрин':'citrine','Агат':'agate','Оникс':'onyx','Яшма':'jasper','Обсидиан':'obsidian','Флюорит':'fluorite','Кальцит':'calcite','Пирит':'pyrite','Гематит':'hematite','Магнетит':'magnetite','Авантюрин':'aventurine','Амазонит':'amazonite','Лабрадорит':'labradorite','Родонит':'rhodonite','Селенит':'selenite','Шунгит':'shungite','Кианит':'kyanite','Циркон':'zircon','Корунд':'corundum','Рубин':'ruby','Сапфир':'sapphire','Нефрит':'nephrite','Жадеит':'jadeite','Морганит':'morganite','Гелиодор':'heliodor','Гошенит':'goshenite','Апатит':'apatite','Содалит':'sodalite','Танзанит':'tanzanite'
}
CONTENT_TYPES = ['Минерал дня','Где и как образуется','Интересный факт','История и культура','Ювелирное применение','Мифы и факты','Как отличить','Уход и хранение']


def db():
    c = sqlite3.connect(os.path.join(BASE_DIR, 'minerals.db'), timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS minerals(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,last_post TEXT);
        CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY,mineral TEXT,content_type TEXT,title TEXT,body TEXT,image_url TEXT,source_url TEXT,source_domain TEXT,license TEXT,image_sha256 TEXT,image_phash TEXT,published_at TEXT,status TEXT NOT NULL DEFAULT 'draft',error TEXT);
        CREATE TABLE IF NOT EXISTS images(id INTEGER PRIMARY KEY,mineral TEXT,image_url TEXT UNIQUE,source_url TEXT,source_domain TEXT,license TEXT,width INTEGER,height INTEGER,bytes INTEGER,sha256 TEXT,phash TEXT,score REAL,used_at TEXT,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS scheduler(slot TEXT PRIMARY KEY,mineral TEXT,content_type TEXT,post_id INTEGER,status TEXT,updated_at TEXT);
        ''')
        for m in MINERALS:
            c.execute('INSERT OR IGNORE INTO minerals(name) VALUES(?)', (m,))
        c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)', ('auto_enabled', '1' if AUTO_ENABLED else '0'))
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', ('post_times', ','.join(POST_TIMES)))


def norm(s):
    return re.sub(r'\s+', ' ', (s or '').strip()).lower()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def phash(data):
    try:
        im = Image.open(io.BytesIO(data)).convert('L').resize((16, 16))
        px = list(im.getdata()); avg = sum(px) / len(px)
        bits = ''.join('1' if x >= avg else '0' for x in px)
        return hex(int(bits, 2))[2:].zfill(64)
    except Exception:
        return ''


def hamming(a, b):
    try:
        return bin(int(a, 16) ^ int(b, 16)).count('1') if a and b else 999
    except Exception:
        return 999


def get_json(url, params, timeout=20):
    r = requests.get(url, params=params, headers={'User-Agent': USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def wikipedia_extract(mineral):
    try:
        j = get_json(WIKIPEDIA_API, {'action':'query','prop':'extracts','explaintext':1,'titles':mineral,'format':'json','redirects':1}, 15)
        for p in j.get('query', {}).get('pages', {}).values():
            if p.get('extract'):
                return p['extract'][:12000], f'https://ru.wikipedia.org/wiki/{quote_plus(mineral)}'
    except Exception as e:
        log.warning('Wikipedia: %s', e)
    return '', ''


def llm_one_shot(mineral, facts):
    system = '''Ты — редактор Telegram-канала о минералах и камнях.
Напиши ОДИН ГОТОВЫЙ ПОЛНЫЙ ПОСТ ДЛЯ TELEGRAM-ПОСТА С МЕДИА (фотографией минерала).
Пост должен быть компактным, содержательным и законченным — без лишней воды.
Используй ТОЛЬКО два раздела:
🔹 Основные характеристики
🔮 Эзотерические свойства
В эзотерическом разделе явно отделяй традиционные представления от научных фактов.
Заверши пост полноценным предложением и фразой: «Традиционные представления, не научно доказанные свойства.»
Не обрезай мысль, не используй многоточия вместо законченного текста.
Не используй Markdown-кодовые блоки и HTML.
Не добавляй источник фотографии: он будет добавлен программой.
Верни только готовый текст поста, без комментариев.'''
    prompt = f'''Минерал: {mineral}

Справочные данные:
{facts[:5000] if facts else 'Нет справочных данных; используй общеизвестные сведения и не выдумывай специфические числа.'}

Напиши компактный готовый Telegram-пост с медиа. Не превращай его в энциклопедическую статью.'''

    providers = []
    if GROQ_API_KEY:
        providers.append(('groq', GROQ_BASE_URL, GROQ_API_KEY, GROQ_MODEL))
    if MISTRAL_API_KEY:
        providers.append(('mistral', MISTRAL_BASE_URL, MISTRAL_API_KEY, MISTRAL_MODEL))
    if not providers:
        raise RuntimeError('No LLM API key configured')

    for name, base, key, model in providers:
        try:
            payload = {
                'model': model,
                'messages': [{'role':'system','content':system},{'role':'user','content':prompt}],
                'max_tokens': LLM_MAX_TOKENS,
                'temperature': 0.45
            }
            r = requests.post(f'{base}/chat/completions', headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'}, json=payload, timeout=LLM_TIMEOUT)
            r.raise_for_status(); data = r.json()
            text = ((data.get('choices') or [{}])[0].get('message') or {}).get('content','').strip()
            text = re.sub(r'^```\w*\s*|\s*```$', '', text).strip()
            if text:
                log.info('one-shot generated provider=%s chars=%d', name, len(text))
                return text, name
        except Exception as e:
            log.warning('%s generation failed: %s', name, e)
    raise RuntimeError('LLM generation failed')


def _query_variants(mineral, max_queries=6):
    en = MINERAL_EN.get(mineral, mineral)
    return [
        f'{en} natural mineral specimen',
        f'{en} crystal specimen natural',
        f'{en} rough mineral specimen',
        f'{en} mineral close up',
        f'{en} mineral specimen museum',
        f'{en} natural crystal macro'
    ][:max_queries]


def google_cse(mineral):
    if not (GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID):
        return []
    out=[]
    for q in _query_variants(mineral):
        try:
            j=get_json('https://www.googleapis.com/customsearch/v1', {'key':GOOGLE_CSE_API_KEY,'cx':GOOGLE_CSE_ID,'q':q,'searchType':'image','num':10,'imgSize':'large','safe':'active'})
            for it in j.get('items',[]):
                u=it.get('link')
                if not u: continue
                out.append({'url':u,'source_url':(it.get('image') or {}).get('contextLink'),'domain':urlparse(it.get('displayLink','')).netloc or 'google','license':'Unknown — Google Images result','title':it.get('title',''),'query':q,'score':8.0})
        except Exception as e:
            log.warning('Google CSE: %s', e)
    return out


def google_html(mineral):
    if not GOOGLE_HTML_ENABLED:
        return []
    out=[]
    for q0 in _query_variants(mineral):
        try:
            r=requests.get('https://www.google.com/search', params={'tbm':'isch','safe':'active','q':q0}, headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36','Accept-Language':'en-US,en;q=0.9'}, timeout=20)
            r.raise_for_status()
            raw=re.findall(r'https?:\\?/\\?/[^"\\\s<>]+|"(https?://[^"\\]+)"', r.text, re.I)
            for m in raw:
                u = m if isinstance(m,str) else m[0]
                if not u: continue
                u=u.replace('\\/','/').replace('\\u003d','=').replace('\\u0026','&').replace('\\u002f','/')
                u=html.unescape(u)
                host=urlparse(u).netloc.lower()
                if not host or any(x in host for x in ('google.com','googleusercontent.com','gstatic.com','ggpht.com','googleapis.com')): continue
                out.append({'url':u,'source_url':f'https://www.google.com/search?tbm=isch&q={quote_plus(q0)}','domain':host,'license':'Unknown — Google Images result','title':q0,'query':q0,'score':7.0})
                if len(out)>=60: break
        except Exception as e:
            log.warning('Google HTML: %s', e)
    seen=set(); ded=[]
    for x in out:
        if x['url'] not in seen:
            seen.add(x['url']); ded.append(x)
    return ded


def wikimedia_search(mineral):
    if not WIKIMEDIA_ENABLED:
        return []
    en=MINERAL_EN.get(mineral,mineral)
    out=[]
    for q in _query_variants(mineral, 4):
        try:
            j=get_json(WIKIMEDIA_API, {'action':'query','generator':'search','gsrsearch':q,'gsrnamespace':6,'gsrlimit':6,'prop':'imageinfo','iiprop':'url|size|extmetadata','iiurlwidth':1400,'format':'json'})
            for p in j.get('query',{}).get('pages',{}).values():
                ii=(p.get('imageinfo') or [{}])[0]; meta=ii.get('extmetadata') or {}; u=ii.get('thumburl') or ii.get('url')
                if not u: continue
                lic=(meta.get('LicenseShortName') or {}).get('value','')
                title=p.get('title','')
                out.append({'url':u,'source_url':f"https://commons.wikimedia.org/wiki/{quote_plus(title.replace(' ','_'))}",'domain':'commons.wikimedia.org','license':lic or 'Wikimedia Commons license','title':title,'query':q,'score':10.0})
        except requests.HTTPError as e:
            if getattr(e.response,'status_code',0)==429:
                log.warning('Wikimedia rate limited; stop Commons for this run')
                break
        except Exception as e:
            log.warning('Wikimedia: %s', e)
    seen=set(); ded=[]
    for x in out:
        if x['url'] not in seen: seen.add(x['url']); ded.append(x)
    return ded


def image_valid(data):
    if not (IMAGE_MIN_BYTES <= len(data) <= IMAGE_MAX_BYTES): return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            w,h=im.size
        return (w,h) if w>=IMAGE_MIN_WIDTH and h>=IMAGE_MIN_HEIGHT else None
    except Exception:
        return None


def image_candidates(mineral):
    allc = google_cse(mineral) + google_html(mineral) + wikimedia_search(mineral)
    bad=('jewelry','jewellery','ring','necklace','earring','bracelet','cabochon','pendant','beads','illustration','render','synthetic','lab grown','amulet','talisman','catalog','shop','product')
    strong=('natural specimen','mineral specimen','rough mineral','crystal specimen','natural crystal','mineral close up')
    out=[]; seen=set()
    for x in allc:
        u=x.get('url','')
        if not u or u in seen: continue
        text=norm(f"{x.get('title','')} {x.get('query','')}")
        if any(t in text for t in bad): x['score']-=8
        if any(t in text for t in strong): x['score']+=5
        if x.get('domain')=='commons.wikimedia.org': x['score']+=3
        if STRICT_LICENSE and x.get('domain')!='commons.wikimedia.org': continue
        seen.add(u); out.append(x)
    return sorted(out, key=lambda x:x.get('score',0), reverse=True)[:max(IMAGE_CANDIDATES,24)]


def download_candidate(c):
    try:
        r=requests.get(c['url'], headers={'User-Agent':USER_AGENT,'Accept':'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'}, timeout=IMAGE_TIMEOUT, allow_redirects=True)
        r.raise_for_status(); valid=image_valid(r.content)
        if not valid: return None
        x=dict(c); x.update(width=valid[0],height=valid[1],bytes=len(r.content),sha256=sha256(r.content),phash=phash(r.content),data=r.content)
        return x
    except Exception as e:
        log.info('image download failed %s: %s', c.get('url'), e)
        return None


def visual_score(x):
    try:
        im=Image.open(io.BytesIO(x['data'])).convert('RGB'); w,h=im.size
        s=0.0
        if min(w,h)>=1200: s+=3
        elif min(w,h)>=900: s+=1.5
        ratio=max(w,h)/max(1,min(w,h))
        if ratio>2.4: s-=3
        small=im.resize((32,32)); px=list(small.getdata())
        neutral=sum(1 for r,g,b in px if r>235 and g>235 and b>235)/len(px)
        if neutral>0.55: s-=2
        elif neutral<0.30: s+=1
        return s
    except Exception:
        return 0.0


def choose_image(mineral):
    with db() as c:
        used=[r['phash'] for r in c.execute("SELECT phash FROM images WHERE phash!='' ORDER BY id DESC LIMIT 500")]
    candidates=image_candidates(mineral)
    ranked=[]
    for c in candidates[:max(IMAGE_DOWNLOAD_CANDIDATES, 8)]:
        x=download_candidate(c)
        if not x: continue
        s=float(x.get('score',0))+visual_score(x)
        text=norm(f"{x.get('title','')} {x.get('query','')} {x.get('source_url','') or ''}")
        if 'museum' in text or 'exhibit' in text or 'exhibition' in text: s-=4
        if 'catalog' in text or 'product' in text or 'shop' in text: s-=5
        if x.get('domain')=='commons.wikimedia.org': s+=2
        for ph in used:
            d=hamming(x.get('phash',''), ph)
            if d<10: s-=14
            elif d<18: s-=5
        x['score']=s; ranked.append(x)
    if not ranked:
        return None
    best=max(ranked, key=lambda x:x['score'])
    log.info('selected image score=%.2f domain=%s', best['score'], best['domain'])
    return best


def publish_sync(bot, mineral, text, image):
    cap = f"{mineral}"
    async def _send():
        await bot.send_photo(chat_id=CHANNEL_ID, photo=io.BytesIO(image['data']), caption=cap)
        await bot.send_message(chat_id=CHANNEL_ID, text=text)
    return _send()


def choose_mineral():
    with db() as c:
        rows=c.execute('SELECT name FROM minerals ORDER BY last_post IS NOT NULL, last_post, id').fetchall()
    return rows[0]['name'] if rows else MINERALS[0]


def save_image_record(mineral, image):
    now=datetime.utcnow().isoformat(timespec='seconds')+'Z'
    with db() as c:
        c.execute('''INSERT OR REPLACE INTO images(mineral,image_url,source_url,source_domain,license,width,height,bytes,sha256,phash,score,used_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (mineral,image['url'],image.get('source_url',''),image.get('domain',''),image.get('license',''),image['width'],image['height'],image['bytes'],image['sha256'],image['phash'],image['score'],now,now))


async def make_post(bot, mineral=None):
    mineral = mineral or choose_mineral()
    facts,_ = wikipedia_extract(mineral)
    text,provider = llm_one_shot(mineral, facts)
    image = choose_image(mineral)
    if not image:
        raise RuntimeError('No valid real photo found')
    await publish_sync(bot, mineral, text, image)
    save_image_record(mineral, image)
    with db() as c:
        c.execute('INSERT INTO posts(mineral,content_type,title,body,image_url,source_url,source_domain,license,image_sha256,image_phash,published_at,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (mineral,'Минерал дня',mineral,text,image['url'],image.get('source_url',''),image.get('domain',''),image.get('license',''),image['sha256'],image['phash'],datetime.utcnow().isoformat(timespec='seconds')+'Z','published'))
        c.execute('UPDATE minerals SET last_post=? WHERE name=?', (datetime.utcnow().isoformat(timespec='seconds')+'Z', mineral))
    log.info('published mineral=%s provider=%s', mineral, provider)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Минералы: бот готов. Для теста используйте /test или /test аметист.')


async def test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mineral = ' '.join(context.args).strip() if context.args else None
    await update.message.reply_text(f'Тестирую {mineral or "минерал дня"}...')
    try:
        await make_post(context.application.bot, mineral)
        await update.message.reply_text('Готово.')
    except Exception:
        log.exception('test failed')
        await update.message.reply_text('Ошибка — смотрите лог сервера.')


async def scheduler_loop(app):
    while True:
        if AUTO_ENABLED:
            # Simple hourly poll with minute match; avoids extra dependencies.
            now=datetime.now()
            hm=now.strftime('%H:%M')
            if hm in POST_TIMES:
                try:
                    await make_post(app.bot)
                except Exception:
                    log.exception('scheduled publish failed')
                await asyncio.sleep(61)
        await asyncio.sleep(20)


async def post_init(app):
    init_db()
    app.bot_data['scheduler_task'] = asyncio.create_task(scheduler_loop(app))


async def post_shutdown(app):
    task=app.bot_data.get('scheduler_task')
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def main():
    if not BOT_TOKEN:
        raise SystemExit('TELEGRAM_BOT_TOKEN is not configured')
    application=(Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build())
    application.add_handler(CommandHandler('start', start_cmd))
    application.add_handler(CommandHandler('test', test_cmd))
    application.run_polling(drop_pending_updates=True)


if __name__=='__main__':
    main()
