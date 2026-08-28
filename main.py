import os, re, io, json, time, sqlite3, hashlib, logging, asyncio, html
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse
from difflib import SequenceMatcher
from contextlib import suppress

import requests
from PIL import Image
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR,'.env'))

BOT_TOKEN=os.getenv('TELEGRAM_BOT_TOKEN','').strip(); CHANNEL_ID=os.getenv('TELEGRAM_CHANNEL_ID','@myminerals').strip(); ADMIN_CHAT_ID=os.getenv('ADMIN_CHAT_ID','').strip()
DB_FILE=os.path.join(BASE_DIR,os.getenv('DB_FILE','minerals.db')); LOCAL_TZ=os.getenv('LOCAL_TZ','Europe/Moscow')
POST_TIMES=[x.strip() for x in os.getenv('POST_TIMES','09:00,18:00').split(',') if x.strip()]
AUTO_ENABLED=os.getenv('AUTO_ENABLED','0')=='1'
CHANNEL_LINK=os.getenv('CHANNEL_LINK','').strip()
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

MINERAL_EN={"Берилл":"beryl","Аквамарин":"aquamarine","Изумруд":"emerald","Аметист":"amethyst","Топаз":"topaz","Турмалин":"tourmaline","Гранат":"garnet","Малахит":"malachite","Лазурит":"lapis lazuli","Опал":"opal","Кварц":"quartz","Розовый кварц":"rose quartz","Цитрин":"citrine","Агат":"agate","Оникс":"onyx","Яшма":"jasper","Обсидиан":"obsidian","Флюорит":"fluorite","Кальцит":"calcite","Пирит":"pyrite","Гематит":"hematite","Магнетит":"magnetite","Авантюрин":"aventurine","Амазонит":"amazonite","Лабрадорит":"labradorite","Родонит":"rhodonite","Селенит":"selenite","Шунгит":"shungite","Кианит":"kyanite","Циркон":"zircon","Корунд":"corundum","Рубин":"ruby","Сапфир":"sapphire","Нефрит":"nephrite","Жадеит":"jadeite","Морганит":"morganite","Гелиодор":"heliodor","Гошенит":"goshenite","Апатит":"apatite","Содалит":"sodalite","Танзанит":"tanzanite"}

def mineral_aliases(mineral):
    en=MINERAL_EN.get(mineral,mineral).lower(); aliases={mineral.lower(),en}
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
        # Runtime settings must survive service restarts; only initialize missing keys.
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',('auto_enabled','1' if AUTO_ENABLED else '0'))
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',('post_times',','.join(POST_TIMES)))
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',('auto_count','2'))
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',('auto_start','09:00'))
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',('auto_last_at',''))

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
    except Exception:return ''
def hamming(a,b):
    try:return bin(int(a,16)^int(b,16)).count('1') if a and b and len(a)==len(b) else 999
    except Exception:return 999

def image_valid(data):
    if not IMAGE_MIN_BYTES<=len(data)<=IMAGE_MAX_BYTES:return None
    try:
        with Image.open(io.BytesIO(data)) as im: im.verify()
        with Image.open(io.BytesIO(data)) as im:w,h=im.size
        return (w,h) if w>=IMAGE_MIN_WIDTH and h>=IMAGE_MIN_HEIGHT else None
    except Exception:return None

def get_json(url,params,timeout=20):
    r=requests.get(url,params=params,headers={'User-Agent':USER_AGENT},timeout=timeout);r.raise_for_status();return r.json()

def wikipedia_extract(mineral):
    try:
        j=get_json(WIKIPEDIA_API,{'action':'query','prop':'extracts','explaintext':1,'titles':mineral,'format':'json','redirects':1},15)
        for p in j.get('query',{}).get('pages',{}).values():
            if p.get('extract'):return p['extract'][:12000],f'https://ru.wikipedia.org/wiki/{quote_plus(mineral)}'
    except Exception as e:log.warning('Wikipedia: %s',e)
    return '',''

def clean_generated_text(value):
    text=str(value or '').strip();text=re.sub(r'<think>.*?</think>','',text,flags=re.S|re.I);text=re.sub(r'```(?:json|html|markdown)?','',text,flags=re.I);text=text.replace('```','');text=re.sub(r'<br\s*/?>','\n',text,flags=re.I);text=re.sub(r'<[^>]+>','',text);text=re.sub(r'\*\*(.*?)\*\*',r'\1',text,flags=re.S);text=re.sub(r'(?m)^\s*#{1,6}\s*','',text);text=re.sub(r'[ \t]+',' ',text);text=re.sub(r'\n{3,}','\n\n',text);return text.strip()

def _query_variants(mineral,image_queries=None):
    en=MINERAL_EN.get(mineral,mineral);qs=[]
    for q in image_queries or []:
        q=clean_generated_text(q)
        if q:qs.append(q)
    if not qs:qs=[f'{en} natural mineral specimen',f'{en} crystal specimen natural',f'{en} rough mineral specimen',f'{en} mineral close up']
    return list(dict.fromkeys(qs[:6]))

def wikimedia_search(mineral,image_queries=None):
    if not WIKIMEDIA_ENABLED:return []
    out=[];en=MINERAL_EN.get(mineral,mineral);queries=_query_variants(mineral,image_queries)[:3]
    queries=list(dict.fromkeys(queries+[f'{en} mineral specimen',f'{en} natural crystal',f'{en} rough specimen']))[:6]
    for q in queries:
        try:
            j=get_json(WIKIMEDIA_API,{'action':'query','generator':'search','gsrsearch':q,'gsrnamespace':6,'gsrlimit':8,'prop':'imageinfo','iiprop':'url|size|extmetadata','iiurlwidth':1400,'format':'json'})
            for p in j.get('query',{}).get('pages',{}).values():
                ii=(p.get('imageinfo') or [{}])[0];meta=ii.get('extmetadata') or {};u=ii.get('thumburl') or ii.get('url')
                if not u:continue
                title=p.get('title','');lic=(meta.get('LicenseShortName') or {}).get('value','');author=re.sub('<[^>]+>',' ',(meta.get('Artist') or {}).get('value',''))
                out.append({'url':u,'source_url':f"https://commons.wikimedia.org/wiki/{quote_plus(title.replace(' ','_'))}",'domain':'commons.wikimedia.org','license':lic or 'Wikimedia Commons license','title':title,'author':author,'score':7.0,'query':q,'en':en})
        except requests.HTTPError as e:
            if getattr(e.response,'status_code',0)==429:log.warning('Wikimedia rate limited (429); skipping Commons for this run');break
            log.warning('Wikimedia: %s',e)
        except Exception as e:log.warning('Wikimedia: %s',e)
    return list({x['url']:x for x in out}.values())

def google_cse(mineral,image_queries=None):
    if not(GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID):return []
    out=[];en=MINERAL_EN.get(mineral,mineral)
    for q in _query_variants(mineral,image_queries):
        try:
            j=get_json('https://www.googleapis.com/customsearch/v1',{'key':GOOGLE_CSE_API_KEY,'cx':GOOGLE_CSE_ID,'q':q,'searchType':'image','num':10,'imgSize':'large','safe':'active'})
            for it in j.get('items',[]):
                u=it.get('link')
                if not u:continue
                out.append({'url':u,'source_url':(it.get('image') or {}).get('contextLink') or it.get('displayLink'),'domain':urlparse(it.get('displayLink','')).netloc or 'google','license':'Unknown — Google Images result','title':it.get('title',''),'score':8.0,'query':q,'en':en})
        except Exception as e:log.warning('Google CSE: %s',e)
    return out

def google_html(mineral,image_queries=None):
    if not GOOGLE_HTML_ENABLED:return []
    out=[]
    for q0 in _query_variants(mineral,image_queries):
        try:
            r=requests.get('https://www.google.com/search',params={'tbm':'isch','safe':'active','q':q0},headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36','Accept-Language':'en-US,en;q=0.9'},timeout=20);r.raise_for_status();h=r.text;raw_urls=[]
            patterns=[r'https?:\\?/\\?/[^"\\\s<>]+',r'"(https?://[^"\\]+)"',r"'(https?://[^'\\]+)'"]
            for pat in patterns:raw_urls.extend(m.group(1) if m.groups() else m.group(0) for m in re.finditer(pat,h,re.I))
            for u in raw_urls:
                u=u.replace('\\/','/').replace('\\u003d','=').replace('\\u0026','&').replace('\\u002f','/');u=html.unescape(u);host=urlparse(u).netloc.lower()
                if not u.startswith('http') or any(x in host for x in ('google.com','googleusercontent.com','gstatic.com','ggpht.com','googleapis.com')):continue
                if host and host not in ('www.google.com','google.com'):out.append({'url':u,'source_url':f'https://www.google.com/search?tbm=isch&q={quote_plus(q0)}','domain':host,'license':'Unknown — Google Images result','title':q0,'score':7.0,'query':q0,'en':MINERAL_EN.get(mineral,mineral)})
                if len(out)>=60:break
        except Exception as e:log.warning('Google HTML: %s',e)
    seen=set();ded=[]
    for x in out:
        if x['url'] not in seen:seen.add(x['url']);ded.append(x)
    return ded

def image_candidates(mineral,image_queries=None):
    cs=google_cse(mineral,image_queries)+google_html(mineral,image_queries)+wikimedia_search(mineral,image_queries);seen=set();out=[]
    bad_terms=('jewelry','jewellery','ring','necklace','earring','bracelet','cabochon','pendant','beads','carving','sculpture','figurine','illustration','render','synthetic','lab grown','healing','amulet','talisman')
    for x in cs:
        u=x.get('url') or '';meta=norm((x.get('title','')+' '+x.get('query','')))
        if not u or u in seen:continue
        if STRICT_LICENSE and x.get('domain')!='commons.wikimedia.org':continue
        if any(t in meta for t in bad_terms):x['score']-=7
        if any(t in meta for t in ('natural specimen','mineral specimen','rough mineral','crystal specimen')):x['score']+=4
        if x.get('domain')=='commons.wikimedia.org':x['score']+=3
        seen.add(u);out.append(x)
    return sorted(out,key=lambda x:x.get('score',0),reverse=True)[:max(IMAGE_CANDIDATES,24)]

def download_image(c):
    try:
        r=requests.get(c['url'],headers={'User-Agent':USER_AGENT,'Accept':'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'},timeout=IMAGE_TIMEOUT,allow_redirects=True);r.raise_for_status();valid=image_valid(r.content)
        if not valid:return None
        x=dict(c);x.update(width=valid[0],height=valid[1],bytes=len(r.content),sha256=sha256(r.content),phash=phash(r.content),data=r.content);return x
    except Exception as e:log.info('image download failed %s: %s',c.get('url'),e);return None

def _image_visual_score(x):
    try:
        im=Image.open(io.BytesIO(x['data'])).convert('RGB');w,h=im.size;score=0.0
        if min(w,h)>=1200:score+=3
        elif min(w,h)>=900:score+=1.5
        if max(w,h)/max(1,min(w,h))>2.4:score-=3
        small=im.resize((32,32));px=list(small.getdata());neutral=sum(1 for r,g,b in px if r>235 and g>235 and b>235)/len(px)
        if neutral>0.55:score-=2
        elif neutral<0.30:score+=1
        return score
    except Exception:return 0.0

def rank_image(mineral,x,used):
    s=float(x.get('score',0));title=norm(x.get('title',''));query=norm(x.get('query',''));en=norm(MINERAL_EN.get(mineral,mineral));text=' '.join((title,query,x.get('source_url','') or '')).lower()
    if en in title:s+=5
    if en in query:s+=2
    if any(t in text for t in ('natural specimen','mineral specimen','rough specimen','crystal specimen','natural crystal','mineral close up')):s+=5
    if any(t in text for t in ('museum','exhibit','exhibition','display case','collection')):s-=4
    if any(t in text for t in ('catalog','shop','store','product','auction')):s-=5
    if any(t in text for t in ('jewelry','jewellery','ring','necklace','earring','bracelet','cabochon','pendant','beads')):s-=10
    if any(t in text for t in ('illustration','render','synthetic','lab grown','healing','amulet','talisman')):s-=10
    if x.get('domain')=='commons.wikimedia.org':s+=3
    if x.get('license') and 'unknown' not in x.get('license','').lower():s+=2
    if min(x.get('width',0),x.get('height',0))>=1000:s+=2
    if max(x.get('width',0),x.get('height',0))/max(1,min(x.get('width',0),x.get('height',0)))>2.2:s-=2
    s+=_image_visual_score(x)
    for ph in used:
        d=hamming(x.get('phash',''),ph)
        if d<10:s-=14
        elif d<18:s-=5
    return s

def choose_image(mineral,image_queries=None):
    with db() as c:used=[r['phash'] for r in c.execute("SELECT phash FROM images WHERE phash!='' ORDER BY id DESC LIMIT 500")]
    candidates=image_candidates(mineral,image_queries);commons=[x for x in candidates if x.get('domain')=='commons.wikimedia.org'];noncommons=[x for x in candidates if x.get('domain')!='commons.wikimedia.org'];ordered=[];seen=set()
    for c in noncommons[:max(8,IMAGE_DOWNLOAD_CANDIDATES)]+commons[:max(8,IMAGE_DOWNLOAD_CANDIDATES)]:
        if c.get('url') not in seen:seen.add(c.get('url'));ordered.append(c)
    good=[]
    for c in ordered:
        x=download_image(c)
        if x:x['score']=rank_image(mineral,x,used);good.append(x);log.info('image candidate: %.1f %s %s',x['score'],x.get('domain',''),x.get('url','')[:120])
    if not good:log.warning('image search produced no downloadable valid candidates for %s',mineral);return None
    good.sort(key=lambda x:x['score'],reverse=True);best=good[0]
    if best['score']<5:log.warning('best image rejected: low relevance score %.1f; candidates=%d',best['score'],len(good));return None
    with db() as c:c.execute('INSERT OR IGNORE INTO images(mineral,image_url,source_url,source_domain,license,width,height,bytes,sha256,phash,score,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(mineral,best['url'],best.get('source_url',''),best.get('domain',''),best.get('license',''),best['width'],best['height'],best['bytes'],best['sha256'],best['phash'],best['score'],datetime.now(timezone.utc).isoformat()))
    log.info('selected image score=%.1f domain=%s source=%s',best['score'],best.get('domain',''),best.get('source_url',''));return best

def llm_request(messages,temperature=.25,max_tokens=None,force_json=False,preferred=None):
    allp=[]
    if GROQ_API_KEY:allp.append((GROQ_BASE_URL,GROQ_API_KEY,GROQ_MODEL,'groq'))
    if MISTRAL_API_KEY:allp.append((MISTRAL_BASE_URL,MISTRAL_API_KEY,MISTRAL_MODEL,'mistral'))
    providers=([x for x in allp if x[3]==preferred]+[x for x in allp if x[3]!=preferred]) if preferred else allp;last=''
    for base,key,model,name in providers:
        payload={'model':model,'messages':messages,'temperature':temperature,'max_tokens':max_tokens or LLM_MAX_TOKENS}
        try:
            r=requests.post(base+'/chat/completions',headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},json=payload,timeout=LLM_TIMEOUT)
            if not r.ok:
                last=f'{name}: HTTP {r.status_code} {r.text[:300]}';continue
            j=r.json();content=(j.get('choices',[{}])[0].get('message',{}).get('content') or '')
            if isinstance(content,list):content=''.join(str(x.get('text','') if isinstance(x,dict) else x) for x in content)
            content=re.sub(r'<think>.*?</think>','',str(content),flags=re.S|re.I).strip()
            if not content:continue
            if force_json:
                try:parse_json(content)
                except Exception as e:last=f'{name}: invalid JSON ({e})';continue
            log.info('LLM success provider=%s model=%s chars=%d',name,model,len(content));return content,name
        except Exception as e:last=f'{name}: {e}'
        log.warning('LLM provider %s failed: %s',name,last)
    raise RuntimeError(last or 'No LLM provider configured')

def parse_json(raw):
    raw=(raw or '').strip();raw=re.sub(r'<think>.*?</think>','',raw,flags=re.S|re.I);raw=re.sub(r'<think>.*?(?=\{)','',raw,flags=re.S|re.I);raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw,flags=re.I|re.S).strip();start=raw.find('{')
    if start<0:raise ValueError('LLM did not return JSON')
    depth=0;in_str=False;esc=False;end=-1
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
    if end<0:raise ValueError('Incomplete JSON from LLM')
    obj=json.loads(raw[start:end])
    if not isinstance(obj,dict):raise ValueError('JSON root must be object')
    return obj

def safe_telegram_html(text):
    text=(text or '').replace('<br/>','\n').replace('<br />','\n').replace('<br>','\n');text=re.sub(r'```(?:html)?|```','',text,flags=re.I);allowed=re.compile(r'</?(?:b|strong|i|em|u|s|code|pre)>|<a\s+href=["\'][^"\']+["\']\s*>|</a>',re.I);tags=[]
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

def _editor_call(messages,temperature=.2,max_tokens=900,preferred='groq'):
    raw,provider=llm_request(messages,temperature=temperature,max_tokens=max_tokens,force_json=False,preferred=preferred);text=clean_generated_text(raw)
    if not text:raise ValueError(f'{provider} returned empty editorial response')
    return text,provider

def _contains_forbidden_application(text):
    low=clean_generated_text(text).lower()
    return bool(re.search(r'(?m)^\s*(?:[💎🔹🌍✨🔮🛠️🧿📌🧭]\s*)?применение\s*(?:[:—-]|$)',low)) or bool(re.search(r'(?i)\bприменение\b\s*:',low))

def _validate_critic_post(post,mineral):
    post=clean_generated_text(post);post=re.sub(r'\n{3,}','\n\n',post).strip()
    if not post:raise ValueError('critic returned empty post')
    if _contains_forbidden_application(post):raise ValueError('critic returned forbidden application section')
    if '...' in post or '…' in post:raise ValueError('critic returned unfinished ellipsis')
    if any(x in norm(post) for x in ('лечит','лечебн','исцеляет','диагност','гарантированно','гарантирует')):raise ValueError('unsafe medical/guaranteed claim')
    lines=post.splitlines()
    if lines and mineral.lower() in norm(lines[0]):post='\n'.join(lines[1:]).strip()
    if len(post)<320:raise ValueError(f'critic post too short: {len(post)}')
    if len(post)>720:raise ValueError(f'critic post too long: {len(post)}')
    if re.search(r'(?im)^\s*(?:🔹|🌍|✨|🔮|💎|📌|🛠️|🧿)\s*(?:характеристики|где встречается|интересный факт|эзотерические свойства|применение)\b',post):raise ValueError('critic returned legacy sectioned format')
    return post

def generate_content_sync(mineral,ctype):
    """Author creates substance; Critic conceptually rewrites it for Telegram."""
    source,source_url=wikipedia_extract(mineral)
    if not source:raise ValueError('no reliable source material')
    source=source[:7000];en=MINERAL_EN.get(mineral,mineral)
    author_prompt=f"""Ты Автор Telegram-канала о минералах.\nНапиши содержательный фактический черновик о минерале «{mineral}». Тема выпуска: {ctype}.\n\nИспользуй только проверяемые сведения из источника. Дай редактору достаточно материала: свойства и внешний вид, географию/образование, один сильный факт и, если уместно, традиционные эзотерические представления с чётким отделением от науки.\n\nНе создавай раздел «Применение», не придумывай факты, не давай медицинских обещаний. Пиши живым русским текстом, без JSON и служебных комментариев. Не пытайся механически уложить черновик в лимит Telegram.\n\nИСТОЧНИК:\n{source}\n\nВерни только черновик автора."""
    author,author_provider=_editor_call([{'role':'system','content':'Ты Автор. Собери содержательный фактический материал для редактора. Не режь содержание ради лимита Telegram.'},{'role':'user','content':author_prompt}],temperature=.35,max_tokens=1200,preferred='groq')
    log.info('author completed: mineral=%s provider=%s chars=%d',mineral,author_provider,len(author))
    critic_prompt=f"""Ты Критик и главный редактор Telegram-канала о минералах.\n\nПрочитай черновик Автора и источник, проверь смысл и ПЕРЕПИШИ материал КОНЦЕПТУАЛЬНО. Не обрезай текст по символам и не сохраняй структуру исходника. Выбери главное, убери повторы, воду и вторичные детали и заново напиши короткий, цельный, интересный пост для Telegram.\n\nМинерал: «{mineral}»\nТема: {ctype}\n\nЧЕРНОВИК АВТОРА:\n{author}\n\nИСТОЧНИК ДЛЯ ПРОВЕРКИ:\n{source}\n\nТребования:\n- примерно 400–650 символов, максимум 720 до добавления заголовка, хештегов и ссылки;\n- цельный литературный текст, а не карточка с обязательными разделами;\n- не используй заголовки «Характеристики», «Где встречается», «Интересный факт», «Эзотерические свойства»;\n- географию и места встречаемости, если они важны, вплети в обычное предложение;\n- оставь 1–2 самых сильных факта;\n- если уместна эзотерика, добавь короткий абзац и отдельной строкой: «Традиционные представления, не научно доказанные свойства.»;\n- РАЗДЕЛ «Применение» ЗАПРЕЩЁН;\n- без медицинских обещаний, гарантий и многоточий;\n- не добавляй название минерала, хештеги, ссылку, источник фотографии или служебные комментарии;\n- если нужно короче — перепиши идеи короче по смыслу, ничего не обрезай посередине.\n\nВерни только готовый текст поста."""
    last_error=None
    for attempt in range(3):
        try:
            prompt=critic_prompt if not attempt else critic_prompt+'\n\nПРЕДЫДУЩИЙ ВАРИАНТ НЕ ПРОШЁЛ ПРОВЕРКУ. Перепиши его заново по смыслу, устрани причину ошибки и сделай текст естественным и короче.'
            critic,critic_provider=_editor_call([{'role':'system','content':'Ты Критик. Ты не режешь строки и не сохраняешь старый шаблон. Ты заново пишешь лучший короткий Telegram-пост на основе материала Автора.'},{'role':'user','content':prompt}],temperature=.18,max_tokens=900,preferred='mistral')
            critic=_validate_critic_post(critic,mineral);log.info('critic completed: mineral=%s provider=%s chars=%d attempt=%d',mineral,critic_provider,len(critic),attempt+1)
            return {'title':f'{mineral}: минерал дня','post':critic,'image_queries':[f'{en} natural mineral specimen',f'{en} crystal specimen natural',f'{en} rough mineral specimen',f'{en} mineral close up'],'hashtags':['минералы',norm(mineral).replace(' ','_'),'камни','кристаллы'],'_author_provider':author_provider,'_critic_provider':critic_provider,'_source_url':source_url}
        except Exception as e:last_error=e;log.warning('critic attempt %d failed: %s',attempt+1,e)
    raise ValueError(str(last_error) if last_error else 'critic failed')

def build_final_caption(data,channel_link=None,photo_source=None):
    post=clean_generated_text(data.get('post',''));title=clean_generated_text(data.get('title',''))
    if not post:raise ValueError('empty post text')
    parts=[]
    if title:parts.append(f'💎 <b>{title}</b>')
    parts.append(post)
    tags=[]
    for x in data.get('hashtags',[])[:5]:
        x=clean_generated_text(x).lstrip('#').replace(' ','_')
        if x and x not in tags:tags.append(x)
    if tags:parts.append(' '.join('#'+x for x in tags))
    link=(channel_link or CHANNEL_LINK or 'https://t.me/myminerals').strip()
    if link:parts.append(link)
    if photo_source:parts.append(f'📷 Источник фото: {photo_source}')
    caption='\n\n'.join(parts)
    if len(caption)>1024 and photo_source:caption='\n\n'.join(parts[:-1])
    if len(caption)>1024:raise ValueError(f'caption exceeds Telegram limit: {len(caption)}')
    return safe_telegram_html(caption)

async def send_post(bot,post_id):
    with db() as c:r=c.execute('SELECT * FROM posts WHERE id=?',(post_id,)).fetchone()
    if not r:return False
    try:
        if not r['image_url']:raise RuntimeError('No image for post')
        rr=requests.get(r['image_url'],headers={'User-Agent':USER_AGENT},timeout=IMAGE_TIMEOUT);rr.raise_for_status()
        if not image_valid(rr.content):raise RuntimeError('stored image is no longer valid')
        caption=build_final_caption({'title':r['title'] or f"{r['mineral']}: минерал дня",'post':r['body'] or '','hashtags':['минералы',norm(r['mineral']).replace(' ','_'),'камни','кристаллы']},channel_link=CHANNEL_LINK or 'https://t.me/myminerals')
        await bot.send_photo(chat_id=CHANNEL_ID,photo=io.BytesIO(rr.content),caption=caption,parse_mode='HTML')
        with db() as c:c.execute("UPDATE posts SET status='published',published_at=?,error='' WHERE id=?",(datetime.now(timezone.utc).isoformat(),post_id))
        mark_posted(r['mineral']);return True
    except Exception as e:
        with db() as c:c.execute("UPDATE posts SET status='error',error=? WHERE id=?",(str(e)[:1000],post_id))
        log.exception('publish failed');return False

async def generate_and_preview(bot,chat_id,mineral=None,ctype=None):
    mineral=mineral or pick_topic();ctype=ctype or 'Минерал дня'
    try:
        data=await asyncio.to_thread(generate_content_sync,mineral,ctype);image=await asyncio.to_thread(choose_image,mineral,data.get('image_queries'))
        if not image:raise RuntimeError('No valid real photo found')
        caption=build_final_caption({'title':data.get('title',''),'post':data.get('post',''),'hashtags':data.get('hashtags',[])},channel_link=CHANNEL_LINK or 'https://t.me/myminerals',photo_source=image.get('source_url') or None)
        await bot.send_photo(chat_id=chat_id,photo=io.BytesIO(image['data']),caption=caption,parse_mode='HTML',reply_markup=bottom_menu());log.info('preview sent: mineral=%s chat_id=%s',mineral,chat_id);return True
    except Exception as e:
        log.warning('preview generation failed: %s',e);await bot.send_message(chat_id=chat_id,text=f'❌ Тестовый пост не создан: {e}',reply_markup=bottom_menu());return False

async def generate_and_publish(bot,mineral=None,ctype=None):
    mineral=mineral or pick_topic();ctype=ctype or CONTENT_TYPES[int(time.time())%len(CONTENT_TYPES)]
    try:
        data=await asyncio.to_thread(generate_content_sync,mineral,ctype);image=await asyncio.to_thread(choose_image,mineral,data.get('image_queries'))
        if not image:raise RuntimeError('No valid real photo found')
        data['body']=data['post']
        if post_duplicate(data['body']):log.warning('generated post is similar to a recent post; publishing anyway')
        pid=register_post(mineral,ctype,data,image)
        if await send_post(bot,pid):return pid
        raise RuntimeError('Telegram publish failed')
    except Exception as e:log.warning('generation/publish failed: %s',e);return None

def auto_interval_seconds():
    try:return 86400.0/max(1,min(100,int(setting('auto_count','2') or 2)))
    except Exception:return 43200.0

def auto_start_today(now):
    raw=setting('auto_start','09:00') or '09:00'
    try:hh,mm=map(int,raw.split(':')[:2]);return now.replace(hour=hh,minute=mm,second=0,microsecond=0)
    except Exception:return now.replace(hour=9,minute=0,second=0,microsecond=0)

async def scheduler_loop(app):
    while not SHUTDOWN.is_set():
        try:
            if setting('auto_enabled','0')=='1':
                now=local_now();last=None;raw=setting('auto_last_at','')
                if raw:
                    try:last=datetime.fromisoformat(raw)
                    except Exception:last=None
                due=now>=auto_start_today(now) and (last is None or (datetime.now(timezone.utc)-last.astimezone(timezone.utc)).total_seconds()>=auto_interval_seconds()-5)
                if due:
                    set_setting('auto_last_at',datetime.now(timezone.utc).isoformat());slot=f'{now.date()} {now:%H:%M:%S}'
                    with db() as c:c.execute("INSERT OR REPLACE INTO scheduler(slot,status,updated_at) VALUES(?,?,?)",(slot,'running',datetime.now(timezone.utc).isoformat()))
                    pid=await generate_and_publish(app.bot)
                    with db() as c:c.execute("UPDATE scheduler SET status=?,post_id=?,updated_at=? WHERE slot=?",('published' if pid else 'error',pid,datetime.now(timezone.utc).isoformat(),slot))
            try:await asyncio.wait_for(SHUTDOWN.wait(),timeout=10)
            except asyncio.TimeoutError:pass
        except asyncio.CancelledError:break
        except Exception:log.exception('scheduler loop');await asyncio.sleep(10)

def bottom_menu():
    return ReplyKeyboardMarkup([['💎 Новый пост','🧪 Тестовый пост'],['⏱ Автопостинг','📊 Статистика'],['⚙️ Частота','▶️ Вкл/Выкл'],['🆔 ID']],resize_keyboard=True,is_persistent=True)
AUTOPOST_INPUT=set()

def is_admin(update):return bool(ADMIN_CHAT_ID) and str(update.effective_chat.id if update.effective_chat else '')==ADMIN_CHAT_ID

async def cmd_start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):return
    await update.message.reply_text('💎 <b>Minerals Engine</b>\n\nОдин пост = фото + текст в одном сообщении.\n🧪 Тестовый пост отправляется только сюда и не публикуется в канал.\nАвтопостинг: от 1 до 100 публикаций в сутки.\n\nУправление всегда доступно в нижнем меню.',parse_mode='HTML',reply_markup=bottom_menu())

async def show_autopost(q,context):
    enabled=setting('auto_enabled','0')=='1';count=setting('auto_count','2');start=setting('auto_start','09:00')
    kb=[[InlineKeyboardButton('1/день',callback_data='freq:1'),InlineKeyboardButton('5/день',callback_data='freq:5'),InlineKeyboardButton('10/день',callback_data='freq:10')],[InlineKeyboardButton('20/день',callback_data='freq:20'),InlineKeyboardButton('50/день',callback_data='freq:50'),InlineKeyboardButton('100/день',callback_data='freq:100')],[InlineKeyboardButton('✏️ Своя частота',callback_data='freq:custom'),InlineKeyboardButton('▶️ Вкл/Выкл',callback_data='auto_toggle')]]
    await q.edit_message_text(f'⏱ <b>Автопостинг</b>\nСтатус: <b>{"ВКЛ" if enabled else "ВЫКЛ"}</b>\nПубликаций в сутки: <b>{count}</b>\nСтарт: <b>{start}</b>\nИнтервал рассчитывается автоматически.',parse_mode='HTML',reply_markup=InlineKeyboardMarkup(kb))

async def callbacks(update,context):
    q=update.callback_query;await q.answer()
    if not is_admin(update):return
    if q.data=='test':await q.edit_message_text('🧪 Создаю тестовый пост…');await generate_and_preview(context.bot,update.effective_chat.id)
    elif q.data=='create':await q.edit_message_text('Создаю и публикую один пост…');pid=await generate_and_publish(context.bot);await q.edit_message_text(f'Готово. post_id={pid}' if pid else 'Ошибка публикации.')
    elif q.data=='stats':
        with db() as c:total=c.execute('SELECT COUNT(*) n FROM posts').fetchone()['n'];pub=c.execute("SELECT COUNT(*) n FROM posts WHERE status='published'").fetchone()['n'];imgs=c.execute('SELECT COUNT(*) n FROM images').fetchone()['n']
        await q.edit_message_text(f'📊 Постов: {total}\nОпубликовано: {pub}\nФото: {imgs}')
    elif q.data in ('times','auto'):await show_autopost(q,context)
    elif q.data=='auto_toggle':set_setting('auto_enabled','0' if setting('auto_enabled','0')=='1' else '1');await show_autopost(q,context)
    elif q.data.startswith('freq:'):
        value=q.data.split(':',1)[1]
        if value=='custom':AUTOPOST_INPUT.add(str(update.effective_chat.id));await q.edit_message_text('✏️ Напишите число от 1 до 100 — столько постов в сутки.')
        else:set_setting('auto_count',str(max(1,min(100,int(value)))));await show_autopost(q,context)

async def cmd_test(update,context):
    if not is_admin(update):return
    mineral=' '.join(context.args) if context.args else pick_topic();await update.message.reply_text(f'🧪 Тестирую {mineral}. В канал ничего не публикую.',reply_markup=bottom_menu());await generate_and_preview(context.bot,update.effective_chat.id,mineral=mineral,ctype='Минерал дня')

async def cmd_id(update,context):
    if is_admin(update):await update.message.reply_text(str(update.effective_chat.id),reply_markup=bottom_menu())

async def handle_menu(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):return
    msg=(update.message.text or '').strip();chat=str(update.effective_chat.id)
    if chat in AUTOPOST_INPUT:
        if msg.isdigit() and 1<=int(msg)<=100:set_setting('auto_count',str(int(msg)));AUTOPOST_INPUT.discard(chat);await update.message.reply_text(f'✅ Автопостинг: {msg} постов/сутки.',reply_markup=bottom_menu())
        else:await update.message.reply_text('Введите целое число от 1 до 100.',reply_markup=bottom_menu())
        return
    if msg=='🧪 Тестовый пост':await update.message.reply_text('🧪 Создаю тестовый пост. В канал он НЕ попадёт.',reply_markup=bottom_menu());await generate_and_preview(context.bot,update.effective_chat.id)
    elif msg=='💎 Новый пост':await update.message.reply_text('Создаю и публикую один пост…',reply_markup=bottom_menu());pid=await generate_and_publish(context.bot);await update.message.reply_text(f'Готово: post_id={pid}' if pid else 'Ошибка публикации.',reply_markup=bottom_menu())
    elif msg=='⏱ Автопостинг':await update.message.reply_text(f'⏱ {setting("auto_count","2")} постов/сутки, старт {setting("auto_start","09:00")}.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⚙️ Частота',callback_data='times'),InlineKeyboardButton('▶️ Вкл/Выкл',callback_data='auto_toggle')]]))
    elif msg=='📊 Статистика':
        with db() as c:total=c.execute('SELECT COUNT(*) n FROM posts').fetchone()['n'];pub=c.execute("SELECT COUNT(*) n FROM posts WHERE status='published'").fetchone()['n'];imgs=c.execute('SELECT COUNT(*) n FROM images').fetchone()['n']
        await update.message.reply_text(f'📊 Постов: {total}\nОпубликовано: {pub}\nФото: {imgs}',reply_markup=bottom_menu())
    elif msg=='⚙️ Частота':await update.message.reply_text('Выберите частоту 1–100 постов в сутки:',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('1',callback_data='freq:1'),InlineKeyboardButton('5',callback_data='freq:5'),InlineKeyboardButton('10',callback_data='freq:10'),InlineKeyboardButton('20',callback_data='freq:20')],[InlineKeyboardButton('50',callback_data='freq:50'),InlineKeyboardButton('100',callback_data='freq:100'),InlineKeyboardButton('✏️ Своя',callback_data='freq:custom')]]))
    elif msg=='▶️ Вкл/Выкл':v='0' if setting('auto_enabled','0')=='1' else '1';set_setting('auto_enabled',v);await update.message.reply_text(f'Автопостинг: {"ВКЛ" if v=="1" else "ВЫКЛ"}',reply_markup=bottom_menu())
    elif msg=='🆔 ID':await update.message.reply_text(chat,reply_markup=bottom_menu())

async def post_init(app):
    global SCHEDULER_TASK;init_db();SHUTDOWN.clear();SCHEDULER_TASK=asyncio.create_task(scheduler_loop(app),name='minerals-scheduler')
async def post_shutdown(app):
    global SCHEDULER_TASK;SHUTDOWN.set()
    if SCHEDULER_TASK:SCHEDULER_TASK.cancel();await asyncio.gather(SCHEDULER_TASK,return_exceptions=True);SCHEDULER_TASK=None

def main():
    if not BOT_TOKEN:raise SystemExit('TELEGRAM_BOT_TOKEN is required')
    init_db();app=Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build();app.add_handler(CommandHandler('start',cmd_start));app.add_handler(CommandHandler('test',cmd_test));app.add_handler(CommandHandler('id',cmd_id));app.add_handler(CallbackQueryHandler(callbacks));app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle_menu));app.run_polling(allowed_updates=Update.ALL_TYPES)
if __name__=='__main__':main()
