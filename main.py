import os, re, io, json, time, sqlite3, hashlib, logging, asyncio, html
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse
from difflib import SequenceMatcher
from contextlib import suppress

import requests
from PIL import Image
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR,'.env'))

BOT_TOKEN=os.getenv('TELEGRAM_BOT_TOKEN','').strip(); CHANNEL_ID=os.getenv('TELEGRAM_CHANNEL_ID','@myminerals').strip(); ADMIN_CHAT_ID=os.getenv('ADMIN_CHAT_ID','').strip()
DB_FILE=os.path.join(BASE_DIR,os.getenv('DB_FILE','minerals.db')); LOCAL_TZ=os.getenv('LOCAL_TZ','Europe/Moscow')
POST_TIMES=[x.strip() for x in os.getenv('POST_TIMES','09:00,18:00').split(',') if x.strip()]
AUTO_ENABLED=os.getenv('AUTO_ENABLED','0')=='1'
GROQ_API_KEY=os.getenv('GROQ_API_KEY','').strip(); GROQ_BASE_URL=os.getenv('GROQ_BASE_URL','https://api.groq.com/openai/v1').rstrip('/'); GROQ_MODEL=os.getenv('GROQ_MODEL','qwen/qwen3.6-27b').strip()
MISTRAL_API_KEY=os.getenv('MISTRAL_API_KEY','').strip(); MISTRAL_BASE_URL=os.getenv('MISTRAL_BASE_URL','https://api.mistral.ai/v1').rstrip('/'); MISTRAL_MODEL=os.getenv('MISTRAL_MODEL','mistral-small-latest').strip()
LLM_TIMEOUT=int(os.getenv('LLM_TIMEOUT','90')); LLM_MAX_TOKENS=int(os.getenv('LLM_MAX_TOKENS','2200')); FACT_CHECK_ENABLED=os.getenv('FACT_CHECK_ENABLED','1')!='0'; FACT_CHECK_THRESHOLD=float(os.getenv('FACT_CHECK_THRESHOLD','0.72') or 0.72)
GOOGLE_CSE_API_KEY=os.getenv('GOOGLE_CSE_API_KEY','').strip(); GOOGLE_CSE_ID=os.getenv('GOOGLE_CSE_ID','').strip(); GOOGLE_HTML_ENABLED=os.getenv('GOOGLE_HTML_ENABLED','1')!='0'
WIKIMEDIA_ENABLED=os.getenv('WIKIMEDIA_ENABLED','1')!='0'; STRICT_LICENSE=os.getenv('STRICT_LICENSE','0')=='1'
IMAGE_MIN_WIDTH=int(os.getenv('IMAGE_MIN_WIDTH','700')); IMAGE_MIN_HEIGHT=int(os.getenv('IMAGE_MIN_HEIGHT','700')); IMAGE_MIN_BYTES=int(os.getenv('IMAGE_MIN_BYTES','25000')); IMAGE_MAX_BYTES=int(os.getenv('IMAGE_MAX_BYTES',str(12*1024*1024))); IMAGE_TIMEOUT=int(os.getenv('IMAGE_TIMEOUT','25')); IMAGE_CANDIDATES=int(os.getenv('IMAGE_CANDIDATES','16')); IMAGE_DOWNLOAD_CANDIDATES=int(os.getenv('IMAGE_DOWNLOAD_CANDIDATES','12'))
WIKIMEDIA_API='https://commons.wikimedia.org/w/api.php'; WIKIPEDIA_API='https://ru.wikipedia.org/w/api.php'; USER_AGENT='MineralsBot/1.1 (+https://github.com/gotock-crypto)'
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s: %(message)s'); log=logging.getLogger('minerals')
for _name in ('httpx','httpcore','telegram','telegram.ext'):
    logging.getLogger(_name).setLevel(logging.WARNING)
MINERALS=['Берилл','Аквамарин','Изумруд','Аметист','Топаз','Турмалин','Гранат','Малахит','Лазурит','Опал','Кварц','Розовый кварц','Цитрин','Агат','Оникс','Яшма','Обсидиан','Флюорит','Кальцит','Пирит','Гематит','Магнетит','Авантюрин','Амазонит','Лабрадорит','Родонит','Селенит','Шунгит','Кианит','Циркон','Корунд','Рубин','Сапфир','Нефрит','Жадеит','Морганит','Гелиодор','Гошенит','Апатит','Содалит','Танзанит']
CONTENT_TYPES=['Минерал дня','Где и как образуется','Интересный факт','История и культура','Ювелирное применение','Мифы и факты','Как отличить','Уход и хранение']

MINERAL_EN={
"Берилл":"beryl","Аквамарин":"aquamarine","Изумруд":"emerald","Аметист":"amethyst","Топаз":"topaz","Турмалин":"tourmaline","Гранат":"garnet","Малахит":"malachite","Лазурит":"lapis lazuli","Опал":"opal","Кварц":"quartz","Розовый кварц":"rose quartz","Цитрин":"citrine","Агат":"agate","Оникс":"onyx","Яшма":"jasper","Обсидиан":"obsidian","Флюорит":"fluorite","Кальцит":"calcite","Пирит":"pyrite","Гематит":"hematite","Магнетит":"magnetite","Авантюрин":"aventurine","Амазонит":"amazonite","Лабрадорит":"labradorite","Родонит":"rhodonite","Селенит":"selenite","Шунгит":"shungite","Кианит":"kyanite","Циркон":"zircon","Корунд":"corundum","Рубин":"ruby","Сапфир":"sapphire","Нефрит":"nephrite","Жадеит":"jadeite","Морганит":"morganite","Гелиодор":"heliodor","Гошенит":"goshenite","Апатит":"apatite","Содалит":"sodalite","Танзанит":"tanzanite"}

def mineral_aliases(mineral):
    en=MINERAL_EN.get(mineral,mineral).lower()
    aliases={mineral.lower(),en}
    # Accept common English naming variants.
    if en=='lapis lazuli': aliases.add('lapis')
    if en=='rose quartz': aliases.add('quartz')
    return aliases
SCHEDULER_TASK=None; SHUTDOWN=asyncio.Event()

def db():
    c=sqlite3.connect(DB_FILE,timeout=30); c.row_factory=sqlite3.Row; return c

def init_db():
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS minerals(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,last_post TEXT); CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY,mineral TEXT,content_type TEXT,title TEXT,body TEXT,image_url TEXT,source_url TEXT,source_domain TEXT,license TEXT,image_sha256 TEXT,image_phash TEXT,published_at TEXT,status TEXT NOT NULL DEFAULT 'draft',error TEXT); CREATE TABLE IF NOT EXISTS images(id INTEGER PRIMARY KEY,mineral TEXT,image_url TEXT UNIQUE,source_url TEXT,source_domain TEXT,license TEXT,width INTEGER,height INTEGER,bytes INTEGER,sha256 TEXT,phash TEXT,score REAL,used_at TEXT,created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS scheduler(slot TEXT PRIMARY KEY,mineral TEXT,content_type TEXT,post_id INTEGER,status TEXT,updated_at TEXT);''')
        for m in MINERALS: c.execute('INSERT OR IGNORE INTO minerals(name) VALUES(?)',(m,))
        c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',('auto_enabled','1' if AUTO_ENABLED else '0'))
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',('post_times',','.join(POST_TIMES)))

def setting(k,d=''):
    with db() as c: r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone(); return r[0] if r else d

def set_setting(k,v):
    with db() as c: c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(k,v))

def norm(s): return re.sub(r'\s+',' ',(s or '').strip()).lower()
def similarity(a,b): return SequenceMatcher(None,norm(a),norm(b)).ratio()
def sha256(b): return hashlib.sha256(b).hexdigest()
def phash(data):
    try:
        im=Image.open(io.BytesIO(data)).convert('L').resize((16,16)); px=list(im.get_flattened_data()) if hasattr(im,'get_flattened_data') else list(im.getdata()); avg=sum(px)/len(px); return hex(int(''.join('1' if x>=avg else '0' for x in px),2))[2:].zfill(64)
    except Exception: return ''
def hamming(a,b):
    try: return bin(int(a,16)^int(b,16)).count('1') if a and b and len(a)==len(b) else 999
    except Exception: return 999

def image_valid(data):
    if not IMAGE_MIN_BYTES<=len(data)<=IMAGE_MAX_BYTES: return None
    try:
        with Image.open(io.BytesIO(data)) as im: im.verify()
        with Image.open(io.BytesIO(data)) as im: w,h=im.size
        return (w,h) if w>=IMAGE_MIN_WIDTH and h>=IMAGE_MIN_HEIGHT else None
    except Exception: return None

def get_json(url,params,timeout=20):
    r=requests.get(url,params=params,headers={'User-Agent':USER_AGENT},timeout=timeout); r.raise_for_status(); return r.json()

def wikipedia_extract(mineral):
    try:
        j=get_json(WIKIPEDIA_API,{'action':'query','prop':'extracts','explaintext':1,'titles':mineral,'format':'json','redirects':1},15)
        for p in j.get('query',{}).get('pages',{}).values():
            if p.get('extract'): return p['extract'][:12000],f'https://ru.wikipedia.org/wiki/{quote_plus(mineral)}'
    except Exception as e: log.warning('Wikipedia: %s',e)
    return '',''

def _query_variants(mineral, image_queries=None):
    en=MINERAL_EN.get(mineral,mineral)
    qs=[]
    for q in image_queries or []:
        q=clean_generated_text(q)
        if q: qs.append(q)
    if not qs:
        qs=[f'{en} natural mineral specimen',f'{en} crystal specimen natural',f'{en} rough mineral specimen',f'{en} mineral close up']
    return list(dict.fromkeys(qs[:6]))

def wikimedia_search(mineral, image_queries=None):
    if not WIKIMEDIA_ENABLED:return []
    out=[]
    en=MINERAL_EN.get(mineral,mineral)
    queries=_query_variants(mineral,image_queries)[:3]
    # Always add deterministic canonical Commons queries. Do not depend on LLM
    # wording for licensed-image discovery.
    canonical=[f'{en} mineral specimen', f'{en} natural crystal', f'{en} rough specimen']
    queries=list(dict.fromkeys(queries+canonical))[:6]
    # Do not hammer Commons: a single 429 disables Commons for this run.
    for q in queries:
        try:
            j=get_json(WIKIMEDIA_API,{'action':'query','generator':'search','gsrsearch':q,'gsrnamespace':6,'gsrlimit':8,'prop':'imageinfo','iiprop':'url|size|extmetadata','iiurlwidth':1400,'format':'json'})
            for p in j.get('query',{}).get('pages',{}).values():
                ii=(p.get('imageinfo') or [{}])[0]; meta=ii.get('extmetadata') or {}; u=ii.get('thumburl') or ii.get('url')
                if not u:continue
                title=p.get('title',''); lic=(meta.get('LicenseShortName') or {}).get('value',''); author=re.sub('<[^>]+>',' ',(meta.get('Artist') or {}).get('value',''))
                out.append({'url':u,'source_url':f"https://commons.wikimedia.org/wiki/{quote_plus(title.replace(' ','_'))}",'domain':'commons.wikimedia.org','license':lic or 'Wikimedia Commons license','title':title,'author':author,'score':7.0,'query':q,'en':en})
        except requests.HTTPError as e:
            if getattr(e.response,'status_code',0)==429:
                log.warning('Wikimedia rate limited (429); skipping Commons for this run')
                break
            log.warning('Wikimedia: %s',e)
        except Exception as e:log.warning('Wikimedia: %s',e)
    return list({x['url']:x for x in out}.values())

def google_cse(mineral, image_queries=None):
    if not(GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID):return []
    out=[]; en=MINERAL_EN.get(mineral,mineral)
    for q in _query_variants(mineral,image_queries):
        try:
            j=get_json('https://www.googleapis.com/customsearch/v1',{'key':GOOGLE_CSE_API_KEY,'cx':GOOGLE_CSE_ID,'q':q,'searchType':'image','num':10,'imgSize':'large','safe':'active'})
            for it in j.get('items',[]):
                u=it.get('link');
                if not u: continue
                out.append({'url':u,'source_url':(it.get('image') or {}).get('contextLink') or it.get('displayLink'),'domain':urlparse(it.get('displayLink','')).netloc or 'google','license':'Unknown — Google Images result','title':it.get('title',''),'score':8.0,'query':q,'en':en})
        except Exception as e:log.warning('Google CSE: %s',e)
    return out

def google_html(mineral, image_queries=None):
    if not GOOGLE_HTML_ENABLED:return []
    out=[]
    for q0 in _query_variants(mineral,image_queries):
        q=quote_plus(q0)
        try:
            r=requests.get('https://www.google.com/search',params={'tbm':'isch','safe':'active','q':q0},headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36','Accept-Language':'en-US,en;q=0.9'},timeout=20)
            r.raise_for_status(); h=r.text
            # Google embeds image metadata in several slightly different JSON forms.
            # Collect absolute image URLs, including escaped URLs and extension-less URLs.
            raw_urls=[]
            patterns=[
                r'https?:\\?/\\?/[^"\\\s<>]+',
                r'"(https?://[^"\\]+)"',
                r"'(https?://[^'\\]+)'",
            ]
            for pat in patterns:
                raw_urls.extend(m.group(1) if m.groups() else m.group(0) for m in re.finditer(pat,h,re.I))
            for u in raw_urls:
                u=u.replace('\\/','/').replace('\\u003d','=').replace('\\u0026','&').replace('\\u002f','/')
                u=html.unescape(u)
                # Strip Google redirect wrappers when present.
                if 'google.com/url?' in u:
                    from urllib.parse import parse_qs
                    try:
                        qv=parse_qs(urlparse(u).query).get('q') or parse_qs(urlparse(u).query).get('url')
                        if qv: u=qv[0]
                    except Exception: pass
                if not u.startswith('http'):continue
                host=urlparse(u).netloc.lower()
                if any(x in host for x in ('google.com','googleusercontent.com','gstatic.com','ggpht.com','googleapis.com')):continue
                # Google often returns extension-less CDN/source URLs. Let the
                # image downloader + Pillow decide whether it is really an image.
                if host and host not in ('www.google.com','google.com'):
                    out.append({'url':u,'source_url':f'https://www.google.com/search?tbm=isch&q={q}','domain':host,'license':'Unknown — Google Images result','title':q0,'score':7.0,'query':q0,'en':MINERAL_EN.get(mineral,mineral)})
                if len(out)>=60:break
        except Exception as e:log.warning('Google HTML: %s',e)
    # de-duplicate while preserving discovery order
    seen=set(); ded=[]
    for x in out:
        if x['url'] not in seen:seen.add(x['url']);ded.append(x)
    return ded

def image_candidates(mineral, image_queries=None):
    # Google is the primary visual discovery source; Commons is the licensed fallback.
    cs=google_cse(mineral,image_queries)+google_html(mineral,image_queries)+wikimedia_search(mineral,image_queries)
    seen=set(); out=[]
    bad_terms=('jewelry','jewellery','ring','necklace','earring','bracelet','cabochon','pendant','beads','carving','sculpture','figurine','illustration','render','synthetic','lab grown','healing','amulet','talisman')
    for x in cs:
        u=x.get('url') or ''; meta=norm((x.get('title','')+' '+x.get('query','')))
        if not u or u in seen:continue
        if STRICT_LICENSE and x.get('domain')!='commons.wikimedia.org':continue
        if any(t in meta for t in bad_terms): x['score']-=7
        if any(t in meta for t in ('natural specimen','mineral specimen','rough mineral','crystal specimen')): x['score']+=4
        # Strong preference for a real specimen and known image host; do not require Commons.
        if x.get('domain')=='commons.wikimedia.org':x['score']+=3
        seen.add(u);out.append(x)
    return sorted(out,key=lambda x:x.get('score',0),reverse=True)[:max(IMAGE_CANDIDATES,24)]

def download_image(c):
    try:
        r=requests.get(c['url'],headers={'User-Agent':USER_AGENT,'Accept':'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'},timeout=IMAGE_TIMEOUT,allow_redirects=True); r.raise_for_status(); valid=image_valid(r.content)
        if not valid:return None
        x=dict(c); x.update(width=valid[0],height=valid[1],bytes=len(r.content),sha256=sha256(r.content),phash=phash(r.content),data=r.content); return x
    except Exception as e:log.info('image download failed %s: %s',c.get('url'),e);return None

def _image_visual_score(x):
    """Prefer a clean, close specimen photo over an exhibit, jewelry, or collage."""
    try:
        im=Image.open(io.BytesIO(x['data'])).convert('RGB')
        w,h=im.size
        # Large specimen photos are preferred. Penalize extreme panoramas.
        score=0.0
        if min(w,h)>=1200: score+=3
        elif min(w,h)>=900: score+=1.5
        ratio=max(w,h)/max(1,min(w,h))
        if ratio>2.4: score-=3
        # Estimate whether the image is visually dominated by a white/neutral border.
        # This helps reject catalog shots with huge empty margins without doing object detection.
        small=im.resize((32,32))
        px=list(small.getdata())
        neutral=sum(1 for r,g,b in px if r>235 and g>235 and b>235)/len(px)
        if neutral>0.55: score-=2
        elif neutral<0.30: score+=1
        return score
    except Exception:
        return 0.0

def rank_image(mineral,x,used):
    s=float(x.get('score',0)); title=norm(x.get('title','')); query=norm(x.get('query','')); en=norm(MINERAL_EN.get(mineral,mineral))
    text=' '.join((title,query,x.get('source_url','') or '')).lower()
    if en in title:s+=5
    if en in query:s+=2
    strong=('natural specimen','mineral specimen','rough specimen','crystal specimen','natural crystal','mineral close up')
    if any(t in text for t in strong):s+=5
    if any(t in text for t in ('museum','exhibit','exhibition','display case','collection')):s-=4
    if any(t in text for t in ('catalog','shop','store','product','auction')):s-=5
    if any(t in text for t in ('jewelry','jewellery','ring','necklace','earring','bracelet','cabochon','pendant','beads')):s-=10
    if any(t in text for t in ('illustration','render','synthetic','lab grown','healing','amulet','talisman')):s-=10
    if x.get('domain')=='commons.wikimedia.org':s+=3
    if x.get('license') and 'unknown' not in x.get('license','').lower():s+=2
    w,h=x.get('width',0),x.get('height',0)
    if min(w,h)>=1000:s+=2
    if max(w,h)/max(1,min(w,h))>2.2:s-=2
    s+=_image_visual_score(x)
    for ph in used:
        d=hamming(x.get('phash',''),ph)
        if d<10:s-=14
        elif d<18:s-=5
    return s

def choose_image(mineral,image_queries=None):
    used=[]
    with db() as c:used=[r['phash'] for r in c.execute("SELECT phash FROM images WHERE phash!='' ORDER BY id DESC LIMIT 500")]
    candidates=image_candidates(mineral,image_queries)
    commons=[x for x in candidates if x.get('domain')=='commons.wikimedia.org']
    noncommons=[x for x in candidates if x.get('domain')!='commons.wikimedia.org']
    # Download enough candidates to rank the actual pixels, not just metadata.
    ordered=[]; seen=set()
    for c in noncommons[:max(8,IMAGE_DOWNLOAD_CANDIDATES)]+commons[:max(8,IMAGE_DOWNLOAD_CANDIDATES)]:
        if c.get('url') not in seen: seen.add(c.get('url')); ordered.append(c)
    good=[]
    for c in ordered:
        x=download_image(c)
        if x:
            x['score']=rank_image(mineral,x,used); good.append(x)
            log.info('image candidate: %.1f %s %s',x['score'],x.get('domain',''),x.get('url','')[:120])
    if not good:
        log.warning('image search produced no downloadable valid candidates for %s',mineral)
        return None
    good.sort(key=lambda x:x['score'],reverse=True)
    best=good[0]
    # Do not fail merely because metadata was sparse: actual pixels have already passed validation.
    if best['score'] < 5:
        log.warning('best image rejected: low relevance score %.1f; candidates=%d',best['score'],len(good)); return None
    with db() as c:c.execute('INSERT OR IGNORE INTO images(mineral,image_url,source_url,source_domain,license,width,height,bytes,sha256,phash,score,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(mineral,best['url'],best.get('source_url',''),best.get('domain',''),best.get('license',''),best['width'],best['height'],best['bytes'],best['sha256'],best['phash'],best['score'],datetime.now(timezone.utc).isoformat()))
    log.info('selected image score=%.1f domain=%s source=%s',best['score'],best.get('domain',''),best.get('source_url',''))
    return best

def llm_request(messages,temperature=.25,max_tokens=None,force_json=False,preferred=None):
    providers=[]; allp=[]
    if GROQ_API_KEY: allp.append((GROQ_BASE_URL,GROQ_API_KEY,GROQ_MODEL,'groq'))
    if MISTRAL_API_KEY: allp.append((MISTRAL_BASE_URL,MISTRAL_API_KEY,MISTRAL_MODEL,'mistral'))
    providers=([x for x in allp if x[3]==preferred]+[x for x in allp if x[3]!=preferred]) if preferred else allp
    last=''
    for base,key,model,name in providers:
        payload={'model':model,'messages':messages,'temperature':temperature,'max_tokens':max_tokens or LLM_MAX_TOKENS}
        # Do not use provider-side JSON mode: Groq/Qwen may reject valid prompts with json_validate_failed.
        # We validate/extract JSON locally with parse_json().
        try:
            r=requests.post(base+'/chat/completions',headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},json=payload,timeout=LLM_TIMEOUT)
            if not r.ok:
                last=f'{name}: HTTP {r.status_code} {r.text[:300]}'
                # One clean retry without provider-side JSON enforcement.
                if force_json and r.status_code in (400,404,422):
                    payload.pop('response_format',None)
                    rr=requests.post(base+'/chat/completions',headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},json=payload,timeout=LLM_TIMEOUT)
                    if rr.ok: r=rr
                    else: continue
                else: continue
            j=r.json(); content=(j.get('choices',[{}])[0].get('message',{}).get('content') or '')
            if isinstance(content,list): content=''.join(str(x.get('text','') if isinstance(x,dict) else x) for x in content)
            content=re.sub(r'<think>.*?</think>','',str(content),flags=re.S|re.I).strip()
            if not content: continue
            if force_json:
                try: parse_json(content)
                except Exception as e: last=f'{name}: invalid JSON ({e})'; continue
            log.info('LLM success provider=%s model=%s chars=%d',name,model,len(content)); return content,name
        except Exception as e: last=f'{name}: {e}'
        log.warning('LLM provider %s failed: %s',name,last)
    raise RuntimeError(last or 'No LLM provider configured')

def parse_json(raw):
    raw=(raw or '').strip()
    # Reasoning models may emit an unclosed <think> block when the token budget is tight.
    raw=re.sub(r'<think>.*?</think>','',raw,flags=re.S|re.I)
    raw=re.sub(r'<think>.*?(?=\{)','',raw,flags=re.S|re.I)
    raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw,flags=re.I|re.S).strip()
    # Prefer fenced-free object; handle extra prose by balanced-brace extraction.
    start=raw.find('{')
    if start<0:raise ValueError('LLM did not return JSON')
    depth=0; in_str=False; esc=False; end=-1
    for i in range(start,len(raw)):
        ch=raw[i]
        if in_str:
            if esc:esc=False
            elif ch=='\\':esc=True
            elif ch=='"':in_str=False
        elif ch=='"':in_str=True
        elif ch=='{':depth+=1
        elif ch=='}':
            depth-=1
            if depth==0:end=i+1;break
    if end<0:
        # Best-effort salvage for a truncated JSON object from a reasoning model.
        candidate=raw[start:]
        candidate=re.sub(r',\s*$', '', candidate)
        candidate=re.sub(r'[,\s]+([}\]])', r'\1', candidate)
        # Close an unfinished string conservatively, then close open arrays/objects.
        if in_str: candidate+='"'
        opens=[]; ins=False; esc2=False
        for ch in candidate:
            if ins:
                if esc2:esc2=False
                elif ch=='\\':esc2=True
                elif ch=='"':ins=False
            elif ch=='"':ins=True
            elif ch in '[{':opens.append(ch)
            elif ch in ']}':
                if opens:opens.pop()
        candidate += ''.join(']' if ch=='[' else '}' for ch in reversed(opens))
        try: return json.loads(candidate)
        except Exception: raise ValueError('Incomplete JSON from LLM')
    obj=json.loads(raw[start:end])
    if not isinstance(obj,dict):raise ValueError('JSON root must be object')
    return obj

def safe_telegram_html(text):
    text=(text or '').replace('<br/>','\n').replace('<br />','\n').replace('<br>','\n')
    # Strip markdown fences and unsupported tags, then escape everything except a small allowlist.
    text=re.sub(r'```(?:html)?|```','',text,flags=re.I)
    allowed=re.compile(r'</?(?:b|strong|i|em|u|s|code|pre)>|<a\s+href=["\'][^"\']+["\']\s*>|</a>',re.I)
    tags=[]
    def stash(m):tags.append(m.group(0));return f'__TG_{len(tags)-1}__'
    escaped=html.escape(allowed.sub(stash,text),quote=False)
    for i,t in enumerate(tags):escaped=escaped.replace(f'__TG_{i}__',t)
    return escaped

def post_duplicate(body):
    with db() as c:rows=c.execute("SELECT body FROM posts WHERE status='published' ORDER BY id DESC LIMIT 100").fetchall()
    return any(similarity(body,r['body'])>=.88 for r in rows)

def register_post(mineral,ctype,data,img,status='draft',error=''):
    with db() as c:
        cur=c.execute('INSERT INTO posts(mineral,content_type,title,body,image_url,source_url,source_domain,license,image_sha256,image_phash,published_at,status,error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(mineral,ctype,data['title'],data['body'],img.get('url') if img else None,img.get('source_url') if img else None,img.get('domain') if img else None,img.get('license') if img else None,img.get('sha256') if img else None,img.get('phash') if img else None,datetime.now(timezone.utc).isoformat() if status=='published' else None,status,error));return cur.lastrowid

def pick_topic():
    with db() as c:r=c.execute("SELECT name FROM minerals WHERE enabled=1 ORDER BY COALESCE(last_post,'') ASC,RANDOM() LIMIT 1").fetchone();return r['name'] if r else MINERALS[0]
def mark_posted(m):
    with db() as c:c.execute('UPDATE minerals SET last_post=? WHERE name=?',(datetime.now(timezone.utc).isoformat(),m))
def local_now():
    from zoneinfo import ZoneInfo
    try:return datetime.now(ZoneInfo(LOCAL_TZ))
    except Exception:return datetime.now(timezone.utc)

def clean_generated_text(value):
    text=str(value or '').strip()
    text=re.sub(r'<think>.*?</think>', '', text, flags=re.S|re.I)
    text=re.sub(r'```(?:json|html|markdown)?', '', text, flags=re.I)
    text=text.replace('```','')
    text=re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text=re.sub(r'<[^>]+>', '', text)
    text=re.sub(r'\*\*(.*?)\*\*', r'\1', text, flags=re.S)
    text=re.sub(r'(?m)^\s*#{1,6}\s*', '', text)
    text=re.sub(r'[ \t]+', ' ', text)
    text=re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def normalize_list(value):
    if isinstance(value, list):
        out=[]
        for x in value:
            t=clean_generated_text(x)
            if t: out.append(t)
        return out
    if isinstance(value, str):
        return [clean_generated_text(x) for x in re.split(r'\n|;|•', value) if clean_generated_text(x)]
    return []

def looks_placeholder(text):
    n=norm(text)
    bad=('...', '…', 'нет данных', 'не указано', 'здесь будет', 'заполните', 'n/a', 'tbd')
    return (not n) or n in bad or len(re.sub(r'[^а-яa-z0-9]', '', n))<8

def validate_content(data, mineral):
    if not isinstance(data, dict): raise ValueError('content is not an object')
    title=clean_generated_text(data.get('title')); intro=clean_generated_text(data.get('intro'))
    chars=normalize_list(data.get('characteristics')); locations=normalize_list(data.get('locations'))
    fact=clean_generated_text(data.get('interesting_fact')); uses=clean_generated_text(data.get('uses'))
    esoteric=clean_generated_text(data.get('esoteric_properties')); esoteric_note=clean_generated_text(data.get('esoteric_note'))
    queries=normalize_list(data.get('image_queries')); hashtags=normalize_list(data.get('hashtags'))
    if looks_placeholder(title) or len(title)<8 or len(title)>90: raise ValueError('invalid title')
    if mineral.lower() not in title.lower(): raise ValueError('title does not contain mineral')
    if len(intro)<120: raise ValueError('intro too short')
    if len(chars)<3: raise ValueError('need at least 3 characteristics')
    if len(locations)<1: raise ValueError('need at least 1 location')
    if len(fact)<80: raise ValueError('interesting fact too short')
    if len(uses)<60: raise ValueError('uses section too short')
    if len(esoteric)<100: raise ValueError('esoteric properties too short')
    if len(esoteric_note)<50: raise ValueError('esoteric note too short')
    if len(queries)<4: raise ValueError('need at least 4 image queries')
    en=MINERAL_EN.get(mineral,mineral).lower()
    # Do not make the LLM's exact wording a hard failure. Normalize each query
    # deterministically so every image search is guaranteed to contain the
    # canonical English mineral name. This prevents needless 4x LLM retries.
    normalized_queries=[]
    for q in queries:
        q=clean_generated_text(q)
        if not q: continue
        if en not in q.lower():
            q=f'{en} {q}'
        normalized_queries.append(q)
    queries=list(dict.fromkeys(normalized_queries))
    if len(queries)<4:
        defaults=[f'{en} natural mineral specimen',f'{en} crystal specimen natural',f'{en} rough mineral specimen',f'{en} mineral close up']
        queries=list(dict.fromkeys(queries+defaults))
    for field in (intro,fact,uses,esoteric,esoteric_note):
        if looks_placeholder(field): raise ValueError('placeholder content')
    data['title']=title; data['intro']=intro; data['characteristics']=chars[:5]; data['locations']=locations[:4]
    data['interesting_fact']=fact; data['uses']=uses; data['esoteric_properties']=esoteric; data['esoteric_note']=esoteric_note
    data['image_queries']=queries[:6]; data['hashtags']=[x.lstrip('#') for x in hashtags[:8] if len(x.lstrip('#'))>=2]
    if len(data['hashtags'])<2: data['hashtags']=[norm(mineral).replace(' ','_'),'минералы']
    return data

def _shorten(text, limit):
    """Shorten prose only at sentence/word boundaries; never leave an ellipsis."""
    text=clean_generated_text(text)
    if len(text)<=limit:return text
    # Prefer complete sentences that fit.
    sentences=re.split(r'(?<=[.!?])\s+', text)
    kept=[]; total=0
    for sentence in sentences:
        sentence=sentence.strip()
        if not sentence: continue
        add=len(sentence) if not kept else len(sentence)+1
        if total+add<=limit:
            kept.append(sentence); total+=add
        else:
            break
    if kept and len(' '.join(kept))>=max(35, int(limit*.62)):
        return ' '.join(kept)
    # If a single sentence is too long, cut at a word boundary and finish cleanly.
    words=text.split()
    out=[]
    for w in words:
        candidate=' '.join(out+[w])
        if len(candidate)>limit: break
        out.append(w)
    result=' '.join(out).rstrip(' ,;:-')
    return result

def _compact_list(items, max_items, item_limit):
    return [_shorten(x,item_limit) for x in items[:max_items] if clean_generated_text(x)]

def build_body(data):
    intro=_shorten(data['intro'],155)
    chars=_compact_list(data.get('characteristics',[]),3,78)
    locs=_compact_list(data.get('locations',[]),2,68)
    fact=_shorten(data['interesting_fact'],105)
    uses=_shorten(data['uses'],82)
    esoteric=_shorten(data['esoteric_properties'],100)
    note=_shorten(data['esoteric_note'],68)
    parts=[intro,
           '<b>🔹 Основные характеристики</b>\n' + '\n'.join('• '+x for x in chars),
           '<b>🌍 Где встречается</b>\n' + '\n'.join('• '+x for x in locs),
           '<b>✨ Интересный факт</b>\n' + fact,
           '<b>💎 Применение</b>\n' + uses,
           '<b>🔮 Эзотерические свойства</b>\n' + esoteric + '\n\n<i>Традиционные представления, не научно доказанные свойства.</i>\n' + note]
    tags=' '.join('#'+x.lstrip('#') for x in data.get('hashtags',[])[:4])
    if tags: parts.append(tags)
    return '\n\n'.join(parts)

def compact_body(data, max_chars=790):
    """Fit the body below a conservative caption budget using complete units."""
    # Work from a copy-like set of increasingly compact budgets. Never slice the final body.
    profiles=[
        (155,3,78,2,68,105,82,100,68,4),
        (135,3,70,2,60,92,72,88,58,3),
        (120,3,62,2,54,82,64,78,52,2),
        (105,3,55,2,48,72,58,70,46,0),
    ]
    original={k:data.get(k) for k in ('intro','characteristics','locations','interesting_fact','uses','esoteric_properties','esoteric_note','hashtags')}
    for intro_cap,nc,char_cap,nl,loc_cap,fact_cap,uses_cap,eso_cap,note_cap,htags in profiles:
        data['intro']=_shorten(original['intro'] or '',intro_cap)
        data['characteristics']=_compact_list(original['characteristics'] or [],nc,char_cap)
        data['locations']=_compact_list(original['locations'] or [],nl,loc_cap)
        data['interesting_fact']=_shorten(original['interesting_fact'] or '',fact_cap)
        data['uses']=_shorten(original['uses'] or '',uses_cap)
        data['esoteric_properties']=_shorten(original['esoteric_properties'] or '',eso_cap)
        data['esoteric_note']=_shorten(original['esoteric_note'] or '',note_cap)
        data['hashtags']=(original['hashtags'] or [])[:htags]
        body=safe_telegram_html(build_body(data))
        plain=re.sub(r'<[^>]+>','',body)
        if len(plain)<=max_chars:
            return body
    # Last deterministic fallback: keep all required sections but use one short sentence each.
    data['intro']=_shorten(original['intro'] or '',90)
    data['characteristics']=_compact_list(original['characteristics'] or [],3,45)
    data['locations']=_compact_list(original['locations'] or [],2,40)
    data['interesting_fact']=_shorten(original['interesting_fact'] or '',58)
    data['uses']=_shorten(original['uses'] or '',52)
    data['esoteric_properties']=_shorten(original['esoteric_properties'] or '',68)
    data['esoteric_note']=_shorten(original['esoteric_note'] or '',45)
    data['hashtags']=[]
    body=safe_telegram_html(build_body(data)); plain=re.sub(r'<[^>]+>','',body)
    if len(plain)>max_chars:
        raise ValueError(f'assembled body too long after deterministic compaction: {len(plain)}>{max_chars}')
    return body

def _plain_len(text):
    return len(re.sub(r'<[^>]+>', '', clean_generated_text(text)))

def validate_llm_post(post, mineral):
    post=clean_generated_text(post)
    if not post: raise ValueError('LLM returned empty post')
    if '...' in post or '…' in post: raise ValueError('LLM post contains ellipsis')
    if mineral.lower() not in post.lower(): raise ValueError('post does not contain mineral name')
    low=post.lower()
    # Qwen/Mistral may vary the exact heading wording even when all sections are
    # present. Treat common heading variants as equivalent, but still require
    # clear section markers so the post remains scannable in Telegram.
    def has_section(*patterns):
        return any(re.search(p, low, re.I) for p in patterns)
    required=(
        has_section(r'основн(?:ые|ых)?\s+характерист', r'характеристик(?:и|а)'),
        has_section(r'где\s+встречает', r'месторождени', r'где\s+образу'),
        has_section(r'интересн(?:ый|ого)?\s+факт', r'факт\s*:'),
        has_section(r'применен', r'использован', r'ювелирн(?:ое|ом)\s+применен'),
        has_section(r'эзотерическ', r'эзотерика'),
    )
    if not all(required):
        missing=[]
        labels=('характеристики','где встречается','интересный факт','применение','эзотерические свойства')
        for ok,label in zip(required,labels):
            if not ok: missing.append(label)
        raise ValueError('LLM post is missing required sections: '+', '.join(missing))
    if 'традицион' not in low or 'не науч' not in low: raise ValueError('esoteric disclaimer missing')
    if _plain_len(post)<560: raise ValueError('LLM post too short')
    if _plain_len(post)>800: raise ValueError(f'LLM post exceeds final Telegram body budget: {_plain_len(post)}>800')
    forbidden=('лечит','лечебн','гарантированно','гарантирует','диагност','исцеляет')
    if any(x in low for x in forbidden): raise ValueError('unsafe medical or guaranteed claim')
    return post

def fact_check_content(post, mineral, source):
    if not FACT_CHECK_ENABLED or not source: return post
    prompt=f"""Проверь ГОТОВЫЙ короткий Telegram-пост о минерале «{mineral}».

ИСТОЧНИКОВАЯ СПРАВКА:
{source[:2800]}

ГОТОВЫЙ ПОСТ:
{post}

Верни строго один JSON-объект:
{{"verdict":"pass" или "repair", "confidence": число 0..1, "post":"полный финальный текст поста"}}

Правила:
1) Исправляй только фактические ошибки и явно неподтверждённые конкретные сведения.
2) Сохрани пять разделов: 🔹 Основные характеристики, 🌍 Где встречается, ✨ Интересный факт, 💎 Применение, 🔮 Эзотерические свойства.
3) Эзотерика — только традиционные/народные представления. Обязательно сохрани точную оговорку: «Традиционные представления, не научно доказанные свойства.»
4) Никаких лечебных обещаний, диагностики или гарантированного результата.
5) Не используй Markdown, HTML, <think>, многоточия или пояснения вне JSON.
6) Финальный post: 560–780 символов, цельный, без обрывов. Если исходный пост длиннее — компактно перепиши его, не теряя обязательные разделы.
7) Не добавляй источник фотографии.
"""
    raw,_=llm_request([{'role':'system','content':'Ты строгий фактчекер коротких Telegram-постов о минералах. Возвращай только JSON.'},{'role':'user','content':prompt}],temperature=.05,max_tokens=700)
    checked=parse_json(raw); conf=float(checked.get('confidence',0) or 0); corrected=checked.get('post')
    if not isinstance(corrected,str): raise ValueError('fact checker returned no post')
    corrected=validate_llm_post(corrected,mineral)
    if checked.get('verdict')=='pass' and conf>=FACT_CHECK_THRESHOLD:return corrected
    if conf>=0.60:return corrected
    raise ValueError(f'fact check confidence too low: {conf:.2f}')

def compact_post_llm(post, mineral, target=680):
    """Compact an oversized LLM-authored post with a fresh, tiny LLM context.
    The compacting call is allowed to be shorter than the editorial minimum;
    the final gate is responsible for the Telegram-safe range.
    """
    target=max(560,min(int(target),760))
    prompt=f"""Сожми ГОТОВЫЙ пост о минерале «{mineral}» до {target} символов максимум.
Сохрани смысл и факты. НЕ добавляй новых фактов.
Обязательно оставь пять разделов, даже если в каждом останется по одной короткой фразе:
🔹 Основные характеристики
🌍 Где встречается
✨ Интересный факт
💎 Применение
🔮 Эзотерические свойства
После эзотерического раздела ОБЯЗАТЕЛЬНО дословно оставь:
«Традиционные представления, не научно доказанные свойства.»
Не используй многоточия, Markdown, HTML или пояснения.
Верни только JSON: {{"post":"..."}}

ГОТОВЫЙ ПОСТ:
{post[:1800]}
"""
    # Small output budget prevents reasoning models from producing another huge answer.
    raw,_=llm_request([{'role':'system','content':'Ты редактор коротких Telegram-постов. Возвращай только JSON.'},{'role':'user','content':prompt}],temperature=.0,max_tokens=520)
    obj=parse_json(raw); compact=obj.get('post')
    if not isinstance(compact,str): raise ValueError('compactor returned no post')
    compact=clean_generated_text(compact)
    if _plain_len(compact)>760:
        # One more fresh-context pass, not a growing retry conversation.
        raw,_=llm_request([{'role':'system','content':'Ты сверхкраткий редактор Telegram. Возвращай только JSON.'},{'role':'user','content':f'Сожми этот пост о {mineral} до 680 символов максимум. Сохрани пять разделов и точную фразу «Традиционные представления, не научно доказанные свойства.». Не добавляй фактов. Только JSON {{"post":"..."}}.\n\n{compact[:1500]}'}],temperature=.0,max_tokens=480)
        obj=parse_json(raw); compact=clean_generated_text(obj.get('post'))
    return compact


def llm_text_request(messages, temperature=.35, max_tokens=850):
    """One-shot text generation. No quality-gate retries and no second editorial LLM call."""
    providers=[]
    if GROQ_API_KEY: providers.append((GROQ_BASE_URL,GROQ_API_KEY,GROQ_MODEL,'groq'))
    if MISTRAL_API_KEY: providers.append((MISTRAL_BASE_URL,MISTRAL_API_KEY,MISTRAL_MODEL,'mistral'))
    last=''
    for base,key,model,name in providers:
        try:
            payload={'model':model,'messages':messages,'temperature':temperature,'max_tokens':max_tokens}
            r=requests.post(base+'/chat/completions',headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},json=payload,timeout=LLM_TIMEOUT)
            if r.ok:
                j=r.json(); content=(j.get('choices',[{}])[0].get('message',{}).get('content') or '').strip()
                if content:
                    log.info('one-shot generation provider=%s chars=%d',name,_plain_len(content))
                    return content,name
                last=f'{name}: empty response'
            else:
                last=f'{name}: HTTP {r.status_code} {r.text[:300]}'
                log.warning('one-shot provider %s failed: %s',name,last)
        except Exception as e:
            last=f'{name}: {e}'; log.warning('one-shot provider %s exception: %s',name,e)
    raise RuntimeError(last or 'No LLM provider configured')


def _extract_post_text(raw, mineral):
    """Accept the LLM answer as-is when possible; JSON is optional for compatibility."""
    cleaned=clean_generated_text(raw)
    try:
        obj=parse_json(raw)
        if isinstance(obj,dict):
            title=clean_generated_text(obj.get('title')) or f'{mineral}: минерал дня'
            post=clean_generated_text(obj.get('post') or obj.get('text') or '')
            if post:
                return title,post
    except Exception:
        pass
    # If the model answered with a plain Telegram post, publish that directly.
    title=f'{mineral}: минерал дня'
    lines=[x.strip() for x in cleaned.splitlines() if x.strip()]
    if lines and len(lines[0])<=90 and mineral.lower() in lines[0].lower():
        title=lines[0]
        post='\n'.join(lines[1:]).strip() or cleaned
    else:
        post=cleaned
    return title,post


def _telegram_safe_body(post, mineral):
    """Keep the complete LLM-authored text. No editorial character gate or truncation."""
    post=clean_generated_text(post)
    if not post:
        raise ValueError('LLM returned empty post')
    return safe_telegram_html(post)


def _mineral_agent_text(messages, temperature=.2, max_tokens=900, preferred="groq"):
    """Run one editorial pass as plain text, avoiding fragile provider JSON mode."""
    raw, provider = llm_request(messages, temperature=temperature, max_tokens=max_tokens,
                                force_json=False, preferred=preferred)
    text=clean_generated_text(raw)
    if not text:
        raise ValueError(f"{provider} returned empty editorial response")
    return text, provider


def _validate_agent_final(post,mineral):
    post=clean_generated_text(post); post=re.sub(r'\r\n?','\n',post); post=re.sub(r'\n{3,}','\n\n',post).strip()
    if not post: raise ValueError('final post is empty')
    low=post.lower()
    if any(x in low for x in ('thinking process','analyze user input','source material:','format constraints:','reasoning:','<think>','</think>')): raise ValueError('final post contains service/reasoning text')
    if mineral.lower() not in low: raise ValueError('mineral name missing')
    patterns=(r'основн\w*\s+характеристик',r'где\s+встречает|распростран\w*|месторождени',r'интересн\w*\s+факт',r'применен\w*|использован\w*',r'эзотерическ\w*')
    if any(not re.search(x,low) for x in patterns): raise ValueError('final post is missing required sections')
    if 'традиционные представления, не научно доказанные свойства.' not in low: raise ValueError('esoteric disclaimer missing')
    if '...' in post or '…' in post: raise ValueError('unfinished ellipsis')
    if any(x in low for x in ('лечит','лечебн','исцеляет','диагност','гарантированно','гарантирует')): raise ValueError('unsafe medical/guaranteed claim')
    n=len(re.sub(r'<[^>]+>','',post))
    if n<900 or n>2400: raise ValueError(f'final post length invalid: {n}')
    if post[-1] not in ".!?\"'": raise ValueError('final post appears unfinished')
    return post


def generate_content_sync(mineral,ctype):
    """Three-pass editorial agent: author -> fact checker -> final editor."""
    source,source_url=wikipedia_extract(mineral)
    if not source: raise ValueError('no reliable source material')
    source=source[:3600]
    en=MINERAL_EN.get(mineral,mineral)

    author_prompt=f"""Напиши черновик готового Telegram-поста о минерале «{mineral}».
Тема: {ctype}.

Источник:
{source}

Требования:
- Только факты из источника.
- Живой грамотный русский язык.
- 1000–1800 символов.
- Обязательно пять разделов с заголовками ДОСЛОВНО:
🔹 Основные характеристики
🌍 Где встречается
✨ Интересный факт
💎 Применение
🔮 Эзотерические свойства
- Под каждым заголовком полноценный текст.
- Эзотерику описывай только как традиционные представления.
- Никаких медицинских или гарантированных заявлений.
- В самом конце дословно: Традиционные представления, не научно доказанные свойства.
- Не добавляй reasoning, JSON, Markdown, HTML или служебные комментарии.

Верни ТОЛЬКО текст поста."""
    draft,provider1=_mineral_agent_text([
        {'role':'system','content':'Ты автор научно-популярного Telegram-канала о минералах. Только готовый текст.'},
        {'role':'user','content':author_prompt}], .25,850,'groq')

    critic_prompt=f"""Ты строгий редактор-фактчекер. Проверь черновик о минерале «{mineral}» только по источнику.

ИСТОЧНИК:
{source}

ЧЕРНОВИК:
{draft[:3000]}

Проверь фактические ошибки, выдумки, пять разделов, обрывы, повторы, медицинские обещания,
корректность эзотерики и финальную фразу. Верни КОРОТКИЙ список конкретных исправлений.
Если всё хорошо, верни только OK. Не переписывай весь пост. Не используй JSON."""
    critique,provider2=_mineral_agent_text([
        {'role':'system','content':'Ты строгий фактчекер. Только замечания или OK.'},
        {'role':'user','content':critic_prompt}], .05,400,'mistral')

    final_prompt=f"""Ты финальный редактор Telegram-канала о минералах.

Подготовь окончательный пост о минерале «{mineral}».

ИСТОЧНИК:
{source}

ЧЕРНОВИК:
{draft[:3200]}

ЗАМЕЧАНИЯ ФАКТЧЕКЕРА:
{critique[:1400]}

Полностью перепиши текст с учётом замечаний.

Требования:
- 1000–2200 символов.
- Только факты, подтверждаемые источником.
- Естественный интересный русский язык.
- Все предложения закончены.
- ОБЯЗАТЕЛЬНО используй эти заголовки ДОСЛОВНО:
🔹 Основные характеристики
🌍 Где встречается
✨ Интересный факт
💎 Применение
🔮 Эзотерические свойства
- Под каждым заголовком содержательный текст.
- Эзотерика только как традиционные представления.
- Никаких медицинских обещаний и гарантий.
- Не используй многоточия.
- Не добавляй reasoning, служебный текст, JSON, Markdown или HTML.
- В самом конце ДОСЛОВНО: Традиционные представления, не научно доказанные свойства.

Верни ТОЛЬКО готовый Telegram-пост."""
    final_post,provider3=_mineral_agent_text([
        {'role':'system','content':'Ты финальный редактор. Только готовый текст Telegram-поста.'},
        {'role':'user','content':final_prompt}], .12,1100,'mistral')

    post=_validate_agent_final(final_post,mineral)
    title=f'{mineral}: минерал дня'
    body=safe_telegram_html(post)
    queries=[f'{en} natural mineral specimen',f'{en} crystal specimen natural',f'{en} rough mineral specimen',f'{en} mineral close up']
    hashtags=['минералы',norm(mineral).replace(' ','_')]
    log.info('mineral editorial agent completed: mineral=%s passes=3 providers=%s/%s/%s draft_chars=%d final_chars=%d critic_chars=%d',
             mineral,provider1,provider2,provider3,len(draft),len(post),len(critique))
    return {'title':title,'post':post,'body':body,'image_queries':queries,'hashtags':hashtags,'_provider':provider3,'_source_url':source_url}


async def send_post(bot,post_id):
    with db() as c:r=c.execute('SELECT * FROM posts WHERE id=?',(post_id,)).fetchone()
    if not r:return False
    try:
        title=html.escape(r['title'] or r['mineral'],quote=False)
        plain_body=re.sub(r'<[^>]+>','',r['body'] or '')
        plain_body=html.escape(plain_body,quote=False)
        source_line=f'\n\n📷 <a href="{html.escape(r["source_url"],quote=True)}">Источник фото</a>' if r['source_url'] else ''
        text=f'<b>💎 {title}</b>\n\n{plain_body}{source_line}'

        # Deliberately publish media and text as two separate Telegram messages.
        # This removes the photo-caption limit from the content path and guarantees
        # that the complete LLM-authored text is delivered without truncation.
        if r['image_url']:
            rr=requests.get(r['image_url'],headers={'User-Agent':USER_AGENT},timeout=IMAGE_TIMEOUT);rr.raise_for_status();valid=image_valid(rr.content)
            if not valid:raise RuntimeError('stored image is no longer valid')
            await bot.send_photo(chat_id=CHANNEL_ID,photo=io.BytesIO(rr.content))
        await bot.send_message(chat_id=CHANNEL_ID,text=text,parse_mode='HTML')
        with db() as c:c.execute("UPDATE posts SET status='published',published_at=?,error='' WHERE id=?",(datetime.now(timezone.utc).isoformat(),post_id))
        mark_posted(r['mineral']);return True
    except Exception as e:
        with db() as c:c.execute("UPDATE posts SET status='error',error=? WHERE id=?",(str(e)[:1000],post_id))
        log.exception('publish failed');return False


async def generate_and_publish(bot,mineral=None,ctype=None):
    """Generate once and publish once. Editorial checks are deliberately non-blocking."""
    mineral=mineral or pick_topic(); ctype=ctype or CONTENT_TYPES[int(time.time())%len(CONTENT_TYPES)]
    try:
        data=await asyncio.to_thread(generate_content_sync,mineral,ctype)
        # Do not spend LLM calls on duplicate rejection. Keep a warning only.
        if post_duplicate(data['body']):
            log.warning('one-shot generated post is similar to a recent post; publishing anyway')
        image=await asyncio.to_thread(choose_image,mineral,data.get('image_queries'))
        if not image:
            raise RuntimeError('No valid real photo found')
        pid=register_post(mineral,ctype,data,image)
        if await send_post(bot,pid):
            return pid
        raise RuntimeError('Telegram publish failed')
    except Exception as e:
        log.warning('one-shot generation/publish failed: %s',e)
        return None


async def scheduler_loop(app):
    while not SHUTDOWN.is_set():
        try:
            now=local_now();enabled=setting('auto_enabled','0')=='1'
            if enabled and now.strftime('%H:%M') in [x for x in setting('post_times',','.join(POST_TIMES)).split(',') if x]:
                slot=f'{now.date()} {now:%H:%M}'
                with db() as c:row=c.execute('SELECT status FROM scheduler WHERE slot=?',(slot,)).fetchone()
                if not row:
                    with db() as c:c.execute('INSERT INTO scheduler(slot,status,updated_at) VALUES(?,?,?)',(slot,'running',datetime.now(timezone.utc).isoformat()))
                    pid=await generate_and_publish(app.bot)
                    with db() as c:c.execute('UPDATE scheduler SET status=?,post_id=?,updated_at=? WHERE slot=?',('published' if pid else 'error',pid,datetime.now(timezone.utc).isoformat(),slot))
            try:await asyncio.wait_for(SHUTDOWN.wait(),timeout=20)
            except asyncio.TimeoutError:pass
        except asyncio.CancelledError:break
        except Exception:log.exception('scheduler loop');await asyncio.sleep(10)

async def cmd_start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):return
    kb=[[InlineKeyboardButton('💎 Создать пост',callback_data='create'),InlineKeyboardButton('📊 Статистика',callback_data='stats')],[InlineKeyboardButton('⏰ Частота',callback_data='times'),InlineKeyboardButton('▶️ Автопостинг',callback_data='auto')]]
    await update.message.reply_text('💎 <b>Minerals Engine</b>\n\nРеальные фотографии: Wikimedia Commons + Google Images.\nКонтент: Groq → Mistral fallback.\n\nВыберите действие.',parse_mode='HTML',reply_markup=InlineKeyboardMarkup(kb))
def is_admin(update):return bool(ADMIN_CHAT_ID) and str(update.effective_chat.id if update.effective_chat else '')==ADMIN_CHAT_ID
async def callbacks(update,context):
    q=update.callback_query;await q.answer()
    if not is_admin(update):return
    if q.data=='create':
        await q.edit_message_text('Создаю пост: LLM → реальное фото → публикация…');pid=await generate_and_publish(context.bot);await q.edit_message_text(f'Готово. post_id={pid}' if pid else 'Не удалось создать/опубликовать пост.')
    elif q.data=='stats':
        with db() as c:total=c.execute('SELECT COUNT(*) n FROM posts').fetchone()['n'];pub=c.execute("SELECT COUNT(*) n FROM posts WHERE status='published'").fetchone()['n'];imgs=c.execute('SELECT COUNT(*) n FROM images').fetchone()['n']
        await q.edit_message_text(f'📊 Постов: {total}\nОпубликовано: {pub}\nФото в истории: {imgs}')
    elif q.data=='times':await q.edit_message_text('⏰ Расписание: '+setting('post_times',','.join(POST_TIMES)))
    elif q.data=='auto':
        v='0' if setting('auto_enabled','0')=='1' else '1';set_setting('auto_enabled',v);await q.edit_message_text('Автопостинг: '+('ВКЛ' if v=='1' else 'ВЫКЛ'))
async def cmd_test(update,context):
    if not is_admin(update):return
    mineral=' '.join(context.args) if context.args else pick_topic();await update.message.reply_text(f'Тестирую {mineral}…');pid=await generate_and_publish(context.bot,mineral=mineral,ctype='Минерал дня');await update.message.reply_text(f'post_id={pid}' if pid else 'Ошибка — смотрите лог сервера.')
async def cmd_id(update,context):await update.message.reply_text(str(update.effective_chat.id))
async def post_init(app):
    global SCHEDULER_TASK;init_db();SHUTDOWN.clear();SCHEDULER_TASK=asyncio.create_task(scheduler_loop(app),name='minerals-scheduler')
async def post_shutdown(app):
    global SCHEDULER_TASK;SHUTDOWN.set()
    if SCHEDULER_TASK:SCHEDULER_TASK.cancel();await asyncio.gather(SCHEDULER_TASK,return_exceptions=True);SCHEDULER_TASK=None

def main():
    if not BOT_TOKEN:raise SystemExit('TELEGRAM_BOT_TOKEN is required')
    init_db();app=Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build();app.add_handler(CommandHandler('start',cmd_start));app.add_handler(CommandHandler('test',cmd_test));app.add_handler(CommandHandler('id',cmd_id));app.add_handler(CallbackQueryHandler(callbacks));app.run_polling(allowed_updates=Update.ALL_TYPES)
if __name__=='__main__':main()
