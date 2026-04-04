"""
generate_training_data.py v4
============================
Root-cause fix từ v3:
  Bug v3: Amazon leaf có thể match "Clothing" (generic top-level) → text fallback
  bị skip → nhãn đặc thù (Bicycle Tights, Shirts & Tops...) nhận 0 sample.

Thay đổi chính:
  1. Chạy Amazon match VÀ text match SONG SONG (không if/else)
     → Một product có thể match Clothing (Amazon) + Bicycle Tights (text)
  2. Sau vòng chính: force-fill nhãn 0 mẫu từ long_kws/SYNONYMS
  3. Giảm MIN_SCORE text matching: 4.0 → 2.0 (vẫn require phrase hoặc 2 word keys)
  4. Bỏ TEXT_FALLBACK_BLACKLIST cứng (phrase matching đủ chính xác để tự lọc)
  5. 3-pass variation: title variation → synonym phrases → combos
"""

import gzip
import json
import csv
import re
import os
import glob
from collections import defaultdict
import random

random.seed(42)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
METADATA_GLOB = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\meta_Clothing_Shoes_and_Jewelry.json.gz'
CATEGORY_FILE = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\category.csv'
OUTPUT_FILE   = r'D:\Thực tập MB\Shopping_Research_Agent_V1_2\data\training_data.csv'

MIN_SAMPLES_TARGET = 300   # Mục tiêu tối thiểu mỗi nhãn
BUFFER_SIZE = 10_000

# ─────────────────────────────────────────────
# DYNAMIC MAX SAMPLES
# ─────────────────────────────────────────────
GENERIC_CATEGORIES = {
    'Clothing', 'Apparel & Accessories', 'Underwear & Socks', 'Outfit Sets',
    'Uniforms', 'Activewear', 'Loungewear',
}

def get_max_samples(cat_name: str) -> int:
    if cat_name in GENERIC_CATEGORIES:
        return 2_000
    n = len(cat_name.split())
    if n == 1:  return 3_000
    if n == 2:  return 6_000
    if n == 3:  return 10_000
    return 15_000

# ─────────────────────────────────────────────
# STOP WORDS & GENERIC CLOTHING WORDS
# ─────────────────────────────────────────────
STOP_WORDS = {
    'and', 'or', 'the', 'for', 'of', 'in', 'a', 'an', 'with', 'by', 'at',
    'men', 'women', 'unisex', 'adult', 'kids', 'baby', 'toddler',
    'accessories', 'products', 'items',
}

GENERIC_CLOTHING_WORDS = {
    'dress', 'dresses', 'pant', 'pants', 'shirt', 'shirts',
    'skirt', 'skirts', 'jacket', 'jackets', 'coat', 'coats',
    'suit', 'suits', 'top', 'tops', 'shorts', 'underwear',
    'sock', 'socks', 'bra', 'bras', 'swimsuit', 'swimwear',
    'legging', 'leggings', 'boot', 'boots', 'shoe', 'shoes',
    'belt', 'belts', 'hat', 'hats', 'cap', 'glove', 'gloves',
    'vest', 'vests', 'robe', 'robes', 'uniform', 'uniforms',
    'clothing', 'clothes', 'apparel', 'wear', 'outfit', 'outfits',
    'set', 'sets', 'sleeve', 'sleeves', 'collar', 'jersey',
}

# ─────────────────────────────────────────────
# SYNONYMS
# ─────────────────────────────────────────────
SYNONYMS = {
    "Furisode Kimonos":                  ["furisode", "coming of age kimono", "seijin no hi kimono"],
    "Tomesode & Houmongi Kimonos":       ["tomesode", "houmongi", "homongi", "formal kimono women"],
    "Iromuji Kimonos":                   ["iromuji", "single color kimono", "plain kimono"],
    "Komon Kimonos":                     ["komon", "casual kimono"],
    "Bridal Kimonos":                    ["shiromuku", "uchikake", "wedding kimono"],
    "Kimono Coats":                      ["kimono coat", "michiyuki coat", "kimono style coat"],
    "Kimono Outerwear":                  ["kimono cardigan", "kimono robe", "kimono wrap", "kimono duster"],
    "Haori Jackets":                     ["haori", "haori jacket", "japanese haori"],
    "Yukata":                            ["yukata", "festival kimono", "summer kimono", "yukata robe"],
    "Hakama Trousers":                   ["hakama", "kendo pants", "aikido pants", "hakama pants"],
    "Casual Kimonos":                    ["casual kimono", "everyday kimono", "cotton kimono"],
    "Kimonos":                           ["kimono", "japanese kimono", "traditional kimono"],
    "Baptism & Communion Dresses":       ["baptism dress", "christening dress", "communion dress", "baptismal gown"],
    "Dirndls":                           ["dirndl", "oktoberfest dress", "bavarian dress", "dirndl dress"],
    "Saris & Lehengas":                  ["sari", "saree", "lehenga", "salwar kameez", "anarkali"],
    "Ghillie Suits":                     ["ghillie suit", "sniper suit", "camouflage ghillie", "ghillie camo"],
    "Chaps":                             ["chaps", "leather chaps", "cowboy chaps", "rodeo chaps"],
    "Bicycle Skinsuits":                 ["cycling skinsuit", "aero cycling suit", "bicycle skinsuit", "trisuit cycling"],
    "Bicycle Bibs":                      ["bib shorts cycling", "cycling bib shorts", "bicycle bib", "bib tights cycling"],
    "Bicycle Tights":                    ["cycling tights", "bike tights", "bicycle tights", "cycling leggings"],
    "Bicycle Jerseys":                   ["cycling jersey", "bike jersey", "bicycle jersey", "cycling top jersey"],
    "Bicycle Activewear":                ["cycling activewear", "bicycle activewear", "cycling kit clothing", "cycling wear"],
    "Bicycle Shorts & Briefs":           ["cycling shorts", "bike shorts", "bicycle shorts", "spinning shorts"],
    "Snow Pants & Suits":                ["snow pants", "ski pants", "snowsuit", "ski suit", "snow bibs"],
    "Hunting & Tactical Pants":          ["tactical pants", "hunting pants", "camo pants tactical", "tactical trousers"],
    "Hunting & Fishing Vests":           ["hunting vest", "fishing vest", "tackle vest", "hunting fishing vest"],
    "Hunting Clothing":                  ["hunting camo", "blaze orange hunting", "hunting gear clothing"],
    "Motorcycle Suits":                  ["motorcycle suit", "racing leathers", "moto racing suit"],
    "Motorcycle Jackets":                ["motorcycle jacket", "biker jacket", "moto jacket", "motorbike jacket"],
    "Motorcycle Pants":                  ["motorcycle pants", "moto pants", "motorbike pants", "riding pants motorcycle"],
    "Motorcycle Protective Clothing":    ["motorcycle gear", "moto protective gear", "motorcycle protective wear"],
    "Martial Arts Uniforms":             ["gi", "dobok", "judogi", "karategi", "bjj gi", "martial arts gi"],
    "Martial Arts Shorts":               ["mma shorts", "bjj shorts", "grappling shorts", "fight shorts mma"],
    "Boxing Shorts":                     ["boxing shorts", "boxing trunks", "fighter boxing shorts"],
    "Wrestling Uniforms":                ["wrestling singlet", "singlet wrestling", "wrestling uniform"],
    "Flight Suits":                      ["flight suit", "pilot suit", "aviator suit", "flight jumpsuit"],
    "Officiating Uniforms":              ["referee shirt", "umpire uniform", "referee uniform", "official referee"],
    "Garter Belts":                      ["garter belt", "suspender belt", "lingerie garter belt"],
    "Garters":                           ["garter", "leg garter", "bridal garter", "thigh garter"],
    "Long Johns":                        ["long johns", "thermal underwear", "thermal base layer"],
    "Hosiery":                           ["hosiery", "nylons", "pantyhose", "stockings hosiery", "sheer tights"],
    "Food Service Uniforms":             ["chef uniform", "kitchen uniform", "food service uniform", "restaurant uniform"],
    "Security Uniforms":                 ["security guard uniform", "security shirt uniform", "guard security uniform"],
    "Contractor Pants & Coveralls":      ["work coveralls", "mechanic coveralls", "coveralls work", "bib work overalls"],
    "Rain Suits":                        ["rain suit", "waterproof rain suit", "rain jacket pants set"],
    "Rain Pants":                        ["rain pants", "waterproof pants", "waterproof rain pants"],
    "Paintball Clothing":                ["paintball pants", "paintball jersey", "paintball clothing gear"],
    "Petticoats & Pettipants":           ["petticoat", "pettipant", "crinoline", "slip petticoat"],
    "Leotards & Unitards":               ["leotard", "unitard", "gymnastics leotard", "dance leotard"],
    "Skorts":                            ["skort", "skirt shorts", "skort skirt"],
    "Tuxedos":                           ["tuxedo", "tux formal", "black tie tuxedo"],
    "Pant Suits":                        ["pant suit women", "womens pantsuit", "power suit women"],
    "Skirt Suits":                       ["skirt suit women", "business skirt suit", "pencil skirt suit"],
    "Jumpsuits & Rompers":               ["jumpsuit women", "romper women", "playsuit jumpsuit"],
    "Nightgowns":                        ["nightgown", "nightdress", "sleep gown nightgown"],
    "Sleepwear & Loungewear":            ["sleepwear set", "pajama sleepwear", "lounge wear set"],
    "Shapewear":                         ["shapewear", "body shaper", "waist cincher shapewear"],
    "Breast Petals & Concealers":        ["nipple covers", "breast petals", "pasties nipple", "nipple concealer"],
    "Breast Enhancing Inserts":          ["breast insert", "silicone bra insert", "push up bra insert"],
    "Bra Accessories":                   ["bra extender", "bra accessory", "bra converter"],
    "Bra Straps & Extenders":            ["bra strap", "clear bra strap", "bra extender strap"],
    "Bra Strap Pads":                    ["bra pad", "bra strap cushion", "shoulder pad bra strap"],
    "Underwear Slips":                   ["slip underwear", "half slip", "full length slip", "underskirt slip"],
    "Jock Straps":                       ["jockstrap", "jock strap athletic", "athletic jockstrap"],
    "Chef's Jackets":                    ["chef jacket", "chef coat", "cook jacket"],
    "Chef's Pants":                      ["chef pants", "cook pants", "kitchen chef pants"],
    "Chef's Hats":                       ["chef hat", "toque hat", "chef toque", "cook hat"],
    "White Coats":                       ["white lab coat", "lab coat", "doctor white coat", "medical coat"],
    "Softball Uniforms":                 ["softball uniform", "softball jersey", "softball pants uniform"],
    "Cricket Uniforms":                  ["cricket whites", "cricket uniform", "cricket jersey whites"],
    "Cheerleading Uniforms":             ["cheer uniform", "cheerleader outfit", "cheerleading outfit"],
    "Hockey Uniforms":                   ["hockey jersey", "ice hockey jersey", "hockey uniform"],
    "American Football Pants":           ["football pants", "football girdle pants"],
    "American Football Uniforms":        ["football uniform", "american football jersey", "football game uniform"],
    "Basketball Uniforms":               ["basketball jersey", "basketball game uniform", "bball jersey"],
    "Soccer Uniforms":                   ["soccer jersey", "football soccer kit", "soccer uniform kit"],
    "Baseball Uniforms":                 ["baseball uniform", "baseball jersey", "baseball pants uniform"],
    "Sports Uniforms":                   ["sports team uniform", "athletic team uniform", "game uniform sports"],
    "Uniforms":                          ["work uniform", "professional uniform", "staff uniform"],
    "Lingerie Accessories":              ["lingerie accessory", "garter clip", "stocking suspender"],
    "Traditional Leather Pants":         ["leather pants", "lederhosen", "leather trousers traditional"],
    "Japanese Black Formal Wear":        ["montsuki", "haori hakama set", "black formal kimono"],
    "Traditional & Ceremonial Clothing": ["hanbok", "ao dai", "cheongsam", "qipao", "dashiki", "kaftan"],
    "Religious Ceremonial Clothing":     ["clergy robe", "vestment robe", "church robe", "surplice vestment"],
    "Military Uniforms":                 ["military uniform", "army uniform", "tactical military"],
    "Dance Dresses, Skirts & Costumes":  ["dance dress", "dance costume", "ballroom dress", "latin dance costume"],
    "Overalls":                          ["overalls bib", "bib overalls", "dungarees overalls"],
    "School Uniforms":                   ["school uniform", "student uniform", "school dress uniform"],
    "Baby One-Pieces":                   ["baby onesie", "infant bodysuit", "baby snap bodysuit"],
    "Baby & Toddler Diaper Covers":      ["diaper cover", "diaper bloomer", "baby diaper cover"],
    "Baby & Toddler Socks & Tights":     ["baby socks", "infant socks", "toddler socks tights"],
    "Baby & Toddler Tops":               ["baby shirt", "infant top shirt", "toddler top"],
    "Baby & Toddler Bottoms":            ["baby pants", "infant pants bottom", "toddler pants bottom"],
    "Baby & Toddler Dresses":            ["baby dress", "infant dress", "toddler dress girl"],
    "Baby & Toddler Outerwear":          ["baby jacket", "infant jacket coat", "toddler jacket"],
    "Baby & Toddler Outfits":            ["baby outfit set", "infant outfit set", "toddler outfit"],
    "Baby & Toddler Sleepwear":          ["baby pajamas", "infant sleeper", "baby sleep sack"],
    "Baby & Toddler Swimwear":           ["baby swimsuit", "infant swimwear", "toddler swim"],
    "Baby & Toddler Clothing":           ["baby clothes", "infant clothing", "newborn clothes"],
    "Lingerie":                          ["lingerie set", "sexy lingerie", "lace lingerie"],
    "Robes":                             ["bathrobe", "bath robe", "dressing gown robe"],
    "Pajamas":                           ["pajamas", "pyjamas", "pajama set"],
    "Coats & Jackets":                   ["winter coat", "down jacket", "parka jacket"],
    "Toddler Underwear":                 ["toddler underwear", "training pants toddler", "potty training pants"],
    "Long Skirts":                       ["maxi skirt", "long maxi skirt", "floor length skirt"],
    "Mini Skirts":                       ["mini skirt", "micro mini skirt", "short mini skirt"],
    "Knee-Length Skirts":                ["knee length skirt", "midi skirt", "pencil midi skirt"],
    "Wedding Dresses":                   ["wedding dress", "bridal gown", "wedding gown"],
    "Wedding & Bridal Party Dresses":    ["bridesmaid dress", "maid of honor dress", "bridal party dress"],
    "Bridal Party Dresses":              ["bridesmaid gown", "flower girl dress", "bridal maid dress"],
    "Shirts & Tops":                     ["womens shirts tops", "mens shirts tops", "casual shirt top", "fashion top shirt"],
    "Outfit Sets":                       ["matching outfit set", "two piece set outfit", "coordinates outfit"],
    "Underwear & Socks":                 ["underwear socks bundle", "underwear sock set", "socks underwear pack"],
    "Apparel & Accessories":             ["clothing accessories", "apparel accessories set", "fashion accessories"],
    "Nightgowns":                        ["nightgown sleepwear", "chemise nightgown", "sleep nightgown"],
    "One-Pieces":                        ["one piece bodysuit", "one piece swimsuit", "unitard one piece"],
    "Dresses":                           ["womens dress", "casual dress", "summer dress women"],
    "Pants":                             ["womens pants", "mens trousers", "casual trousers"],
    "Shorts":                            ["womens shorts", "casual shorts", "athletic shorts"],
    "Skirts":                            ["womens skirt", "casual fashion skirt", "flared skirt"],
    "Socks":                             ["ankle socks", "crew socks", "athletic socks pair"],
    "Bras":                              ["sports bra", "bralette", "bra underwire women"],
    "Underwear":                         ["womens underwear briefs", "mens underwear boxer", "underwear briefs"],
    "Swimwear":                          ["womens swimwear", "bikini swimwear", "one piece swimwear"],
    "Outerwear":                         ["womens outerwear", "winter outerwear jacket", "outdoor winter jacket"],
    "Suits":                             ["mens suit", "business formal suit", "suit blazer pants"],
    "Vests":                             ["mens vest", "puffer vest", "casual vest"],
    "Activewear":                        ["womens activewear", "workout activewear", "gym activewear"],
    "Loungewear":                        ["womens loungewear", "cozy loungewear", "lounge wear home"],
}

# ─────────────────────────────────────────────
# TEXT CLEANING
# ─────────────────────────────────────────────
_RE_HTML     = re.compile(r'<[^>]+>')
_RE_NOISE    = re.compile(r'\b(pack|set|lot|bundle|qty|quantity|piece|count)\s+of\s+\d+\b', re.I)
_RE_BRACKET  = re.compile(r'[\[\(][^\]\)]{0,40}[\]\)]')
_RE_SPECIAL  = re.compile(r'[^\w\s\-\'\,\.]')
_RE_SPACES   = re.compile(r'\s{2,}')
_RE_PIPE     = re.compile(r'\s*[\|\/\\]\s*.*$')

def clean_title(title: str) -> str:
    if not title or not isinstance(title, str):
        return ""
    t = _RE_HTML.sub(' ', title)
    t = _RE_PIPE.sub('', t)
    t = _RE_BRACKET.sub(' ', t)
    t = _RE_NOISE.sub(' ', t)
    t = _RE_SPECIAL.sub(' ', t)
    t = _RE_SPACES.sub(' ', t)
    return t.strip()

def extract_desc_snippet(desc_field) -> str:
    if not desc_field:
        return ""
    text = ' '.join(str(x) for x in desc_field) if isinstance(desc_field, list) else str(desc_field)
    text = _RE_HTML.sub(' ', text)
    text = _RE_SPECIAL.sub(' ', text)
    return ' '.join(text.split()[:25]).strip()

# ─────────────────────────────────────────────
# PHRASE VARIANTS (singular / plural)
# ─────────────────────────────────────────────
def phrase_variants(phrase: str) -> list:
    variants = {phrase}
    words = phrase.split()
    if not words:
        return [phrase]
    last, prefix = words[-1], words[:-1]

    def add(w):
        variants.add(' '.join(prefix + [w]).strip())

    # Singularize
    if last.endswith('ies') and len(last) > 3:
        add(last[:-3] + 'y')
    elif last.endswith('ses') or last.endswith('xes') or last.endswith('zes'):
        add(last[:-2])
    elif last.endswith('ches') or last.endswith('shes'):
        add(last[:-2])
    elif last.endswith('s') and not last.endswith('ss') and len(last) > 2:
        add(last[:-1])

    # Pluralize
    if last.endswith('y') and len(last) > 2 and last[-2] not in 'aeiou':
        add(last[:-1] + 'ies')
    elif last.endswith(('s', 'x', 'z')):
        add(last + 'es')
    elif last.endswith('ch') or last.endswith('sh'):
        add(last + 'es')
    elif not last.endswith('s'):
        add(last + 's')

    return list(variants)

# ─────────────────────────────────────────────
# LOAD CATEGORIES
# ─────────────────────────────────────────────
def load_categories(file_path):
    categories = []
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            original_name = row['name'].strip()
            if not original_name:
                continue

            clean_name  = original_name.lower()
            extra_syns  = SYNONYMS.get(original_name, [])

            # ── Phrase keywords ──
            all_phrases = set()
            for v in phrase_variants(clean_name):
                all_phrases.add(v)

            words = re.findall(r'\w+', clean_name)
            meaningful_words = [w for w in words if w not in STOP_WORDS and len(w) > 2]
            if len(meaningful_words) >= 2:
                joined = ' '.join(meaningful_words)
                if joined != clean_name:
                    for v in phrase_variants(joined):
                        all_phrases.add(v)

            for syn in extra_syns:
                syn_l = syn.lower().strip()
                if len(syn_l.split()) >= 2:
                    for v in phrase_variants(syn_l):
                        all_phrases.add(v)

            long_kws = list(all_phrases)

            # ── Single distinctive keywords ──
            all_single_words = set(words)
            for syn in extra_syns:
                if len(syn.split()) == 1:
                    all_single_words.add(syn.lower())

            short_kws = [
                w for w in all_single_words
                if w not in STOP_WORDS
                and w not in GENERIC_CLOTHING_WORDS
                and len(w) > 2
            ]
            short_kws = list(set(short_kws))

            # Amazon lookup keys (category name + all synonyms)
            amazon_keys = [clean_name] + [s.lower().strip() for s in extra_syns]

            categories.append({
                'id':            row['id'],
                'original_name': original_name,
                'long_kws':      long_kws,
                'short_kws':     short_kws,
                'amazon_keys':   amazon_keys,
                'is_generic':    original_name in GENERIC_CATEGORIES,
                'max_samples':   get_max_samples(original_name),
            })
    return categories


def build_lookup_indexes(categories):
    amazon_lookup = {}
    word_index    = defaultdict(list)
    phrase_index  = defaultdict(list)

    for cat in categories:
        for ak in cat['amazon_keys']:
            if ak not in amazon_lookup:
                amazon_lookup[ak] = cat
        for ph in cat['long_kws']:
            phrase_index[ph].append(cat)
        for w in cat['short_kws']:
            word_index[w].append(cat)

    return amazon_lookup, word_index, phrase_index

# ─────────────────────────────────────────────
# MATCHING
# ─────────────────────────────────────────────
def match_by_amazon_cat(amazon_cats, amazon_lookup):
    """
    Leaf-first: iterate reversed(amazon_cats), break on first hit.
    amazon_cats = ["Clothing, Shoes & Jewelry", "Women", "Cycling", "Tights"]
    → tries "Tights" first, then "Cycling", then "Women", then top-level.
    """
    if not amazon_cats:
        return None
    for cat_str in reversed(amazon_cats):
        key = cat_str.lower().strip()
        if key in amazon_lookup:
            return amazon_lookup[key]
    return None


def match_by_text_scored(full_text, word_index, phrase_index, min_score=2.0):
    """
    Phrase-first scoring. Returns list of cats sorted by score desc.
    Scoring:
      - n-word phrase match: score += n²  (2-word→4, 3-word→9)
      - 1-word distinctive match: score += 1.0
    Threshold: min_score (default 2.0 = một phrase 2-từ HOẶC hai word match)
    """
    scores  = defaultdict(float)
    matches = {}
    tl = full_text.lower()

    for phrase, cats in phrase_index.items():
        if phrase in tl:
            n = len(phrase.split())
            score = float(n * n)
            for cat in cats:
                scores[cat['id']] += score
                matches[cat['id']] = cat

    words = set(re.findall(r'\b\w+\b', tl))
    for word in words:
        if word in word_index:
            for cat in word_index[word]:
                scores[cat['id']] += 1.0
                if cat['id'] not in matches:
                    matches[cat['id']] = cat

    if not matches:
        return []

    qualified = [(cid, s) for cid, s in scores.items() if s >= min_score]
    if not qualified:
        return []

    qualified.sort(key=lambda x: -x[1])
    return [matches[cid] for cid, _ in qualified[:4]]   # Tối đa 4 cat / product


# ─────────────────────────────────────────────
# VARIATION GENERATION
# ─────────────────────────────────────────────
def generate_variations(title: str) -> list:
    words    = title.split()
    variants = [title]
    if len(words) > 4:
        variants.append(' '.join(words[2:]))
    if len(words) > 4:
        variants.append(' '.join(words[:-2]))
    if len(words) > 6:
        mid = len(words) // 2
        variants.append(' '.join(words[mid-2:mid+2]))

    seen, result = set(), []
    for v in variants:
        v = v.strip()
        if v and len(v.split()) >= 3 and v not in seen:
            seen.add(v)
            result.append(v)
    return result


def make_synonym_combos(phrases: list) -> list:
    """
    Sinh combo query từ các synonym phrases.
    Ghép 2 phrases ngẫu nhiên để tạo query dài hơn → đa dạng hơn.
    """
    combos = []
    multi  = [p for p in phrases if len(p.split()) >= 2]
    for i in range(len(multi)):
        for j in range(i + 1, min(i + 4, len(multi))):
            combo = f"{multi[i]} {multi[j]}"
            if 3 <= len(combo.split()) <= 10:
                combos.append(combo)
    return combos


# ─────────────────────────────────────────────
# ADD ROW HELPER
# ─────────────────────────────────────────────
def try_add(per_cat_rows, per_cat_count, cat_id, cat_name, max_s, query):
    """Thêm 1 row nếu còn chỗ. Trả về True nếu thêm thành công."""
    if per_cat_count[cat_id] >= max_s:
        return False
    per_cat_rows[cat_id].append({
        'category_id':   cat_id,
        'category_name': cat_name,
        'search_query':  query,
    })
    per_cat_count[cat_id] += 1
    return True


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def generate():
    meta_files = sorted(glob.glob(METADATA_GLOB))
    if not meta_files:
        print(f"❌ Không tìm thấy file: {METADATA_GLOB}")
        return

    print(f"✅ Tìm thấy {len(meta_files)} file:")
    for f in meta_files:
        print(f"   - {os.path.basename(f)}")

    print(f"\n📂 Tải danh mục: {CATEGORY_FILE}")
    categories = load_categories(CATEGORY_FILE)
    amazon_lookup, word_index, phrase_index = build_lookup_indexes(categories)
    print(f"   {len(categories)} nhãn | {len(amazon_lookup)} Amazon keys "
          f"| {len(phrase_index)} phrase keys | {len(word_index)} word keys")

    cat_max_map  = {cat['id']: cat['max_samples'] for cat in categories}
    cat_name_map = {cat['id']: cat['original_name'] for cat in categories}

    per_cat_count = defaultdict(int)
    per_cat_rows  = defaultdict(list)
    total_read    = 0
    total_match   = 0
    amazon_hits   = 0
    text_hits     = 0
    both_hits     = 0

    # ──────────────────────────────────────────
    # VÒNG CHÍNH: Đọc metadata
    # ──────────────────────────────────────────
    for meta_file in meta_files:
        fname = os.path.basename(meta_file)
        print(f"\n📖 Đọc: {fname}")
        file_count = 0

        with gzip.open(meta_file, 'rt', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                total_read += 1
                file_count += 1

                # ĐƯA BLOCK LOG LÊN NGAY ĐÂY
                if file_count % 100_000 == 0:
                    matched_cats_n = sum(1 for c in per_cat_count if per_cat_count[c] > 0)
                    print(f"   {file_count:>8,} dòng | rows: {total_match:,} | cats filled: {matched_cats_n}")

                title = clean_title(data.get('title', ''))
                if not title or len(title.split()) < 3:
                    continue

                desc_snippet = extract_desc_snippet(data.get('description', ''))
                full_text    = title + ' ' + desc_snippet

                amazon_cats = data.get('category', [])
                if isinstance(amazon_cats, str):
                    amazon_cats = [amazon_cats]

                # ──────────────────────────────
                # PARALLEL MATCHING — key fix v4
                # Amazon match + text match chạy độc lập, kết hợp kết quả
                # ──────────────────────────────
                matched_dict = {}

                # 1) Amazon leaf-first
                amazon_cat = match_by_amazon_cat(amazon_cats, amazon_lookup)
                if amazon_cat:
                    matched_dict[amazon_cat['id']] = amazon_cat
                    amazon_hits += 1

                # 2) Text phrase scoring — LUÔN chạy (không phụ thuộc Amazon)
                text_cats = match_by_text_scored(full_text, word_index, phrase_index, min_score=2.0)
                for cat in text_cats:
                    if cat['id'] not in matched_dict:
                        matched_dict[cat['id']] = cat
                        text_hits += 1
                    else:
                        both_hits += 1  # Amazon và text cùng match → đếm riêng

                matched_cats = list(matched_dict.values())

                # Ghi rows
                added_any = False
                for cat in matched_cats:
                    cid   = cat['id']
                    max_s = cat_max_map[cid]
                    if try_add(per_cat_rows, per_cat_count, cid, cat['original_name'], max_s, title):
                        total_match += 1
                        added_any = True
                    # Desc snippet bổ sung
                    if (desc_snippet and len(desc_snippet.split()) >= 4
                            and per_cat_count[cid] < max_s):
                        if try_add(per_cat_rows, per_cat_count, cid, cat['original_name'], max_s, desc_snippet):
                            total_match += 1

        print(f"   ✓ Xong {fname}: {file_count:,} dòng")

    # ──────────────────────────────────────────
    # PASS 2: Variation augmentation
    # ──────────────────────────────────────────
    print(f"\n🔧 Pass 2 — Variation augmentation (nhãn < {MIN_SAMPLES_TARGET} mẫu)...")
    variation_added = 0

    for cat in categories:
        cid      = cat['id']
        max_s    = cat['max_samples']
        cat_name = cat['original_name']
        current  = per_cat_count[cid]

        if current >= MIN_SAMPLES_TARGET:
            continue

        need     = min(MIN_SAMPLES_TARGET - current, max_s - current)
        existing = {r['search_query'] for r in per_cat_rows[cid]}
        added    = 0

        # 2a) Title variations từ các rows đã có
        for t in list({r['search_query'] for r in per_cat_rows[cid]}):
            for v in generate_variations(t):
                if added >= need:
                    break
                if v not in existing:
                    if try_add(per_cat_rows, per_cat_count, cid, cat_name, max_s, v):
                        existing.add(v)
                        added += 1
            if added >= need:
                break

        # 2b) Synonym phrases trực tiếp
        for phrase in cat['long_kws']:
            if added >= need:
                break
            if len(phrase.split()) >= 2 and phrase not in existing:
                if try_add(per_cat_rows, per_cat_count, cid, cat_name, max_s, phrase):
                    existing.add(phrase)
                    added += 1

        # 2c) Synonym combos (ghép 2 phrases)
        for combo in make_synonym_combos(cat['long_kws']):
            if added >= need:
                break
            if combo not in existing:
                if try_add(per_cat_rows, per_cat_count, cid, cat_name, max_s, combo):
                    existing.add(combo)
                    added += 1

        variation_added += added

    print(f"   ✓ Thêm {variation_added:,} variation rows")

    # ──────────────────────────────────────────
    # PASS 3: Force-fill nhãn 0 mẫu từ SYNONYMS
    # Chỉ áp dụng cho nhãn vẫn còn 0 sau pass 1+2
    # ──────────────────────────────────────────
    zero_cats = [cat for cat in categories if per_cat_count[cat['id']] == 0]
    if zero_cats:
        print(f"\n🆘 Pass 3 — Force-fill {len(zero_cats)} nhãn 0 mẫu...")
        force_added = 0
        for cat in zero_cats:
            cid      = cat['id']
            max_s    = cat['max_samples']
            cat_name = cat['original_name']
            existing = set()

            # Tất cả phrases từ long_kws + combos
            all_candidates = list(cat['long_kws'])
            all_candidates += make_synonym_combos(cat['long_kws'])
            # Thêm variations của các phrases
            for phrase in list(cat['long_kws'])[:10]:
                for v in generate_variations(phrase + ' clothing'):
                    all_candidates.append(v)

            for q in all_candidates:
                if per_cat_count[cid] >= min(MIN_SAMPLES_TARGET, max_s):
                    break
                if len(q.split()) >= 2 and q not in existing:
                    if try_add(per_cat_rows, per_cat_count, cid, cat_name, max_s, q):
                        existing.add(q)
                        force_added += 1

            if per_cat_count[cid] > 0:
                print(f"   ✓ {cat_name}: {per_cat_count[cid]} mẫu (từ synonyms)")
            else:
                print(f"   ⚠ {cat_name}: vẫn 0 mẫu (thêm synonym vào SYNONYMS dict!)")

        print(f"   ✓ Force-fill thêm {force_added:,} rows")
    else:
        print(f"\n✅ Không có nhãn 0 mẫu sau pass 1+2!")

    # ──────────────────────────────────────────
    # GHI CSV
    # ──────────────────────────────────────────
    print(f"\n💾 Ghi: {OUTPUT_FILE}")
    total_written = 0
    with open(OUTPUT_FILE, mode='w', encoding='utf-8', newline='') as f_out:
        writer = csv.writer(f_out)
        writer.writerow(['category_id', 'category_name', 'search_query'])

        buffer = []
        for rows in per_cat_rows.values():
            for row in rows:
                buffer.append([row['category_id'], row['category_name'], row['search_query']])
                total_written += 1
                if len(buffer) >= BUFFER_SIZE:
                    writer.writerows(buffer)
                    buffer.clear()
        if buffer:
            writer.writerows(buffer)

    # ──────────────────────────────────────────
    # BÁO CÁO
    # ──────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  HOÀN THÀNH — v4")
    print(f"{'='*65}")
    print(f"  Tổng dòng đọc          : {total_read:>10,}")
    print(f"  Match Amazon (leaf)    : {amazon_hits:>10,}")
    print(f"  Match Text (phrase)    : {text_hits:>10,}")
    print(f"  Match cả hai (overlap) : {both_hits:>10,}")
    print(f"  Variation + Force-fill : {variation_added:>10,}")
    print(f"  Tổng dòng ghi ra       : {total_written:>10,}")
    print(f"{'='*65}")

    sorted_cats = sorted(per_cat_count.items(), key=lambda x: x[1])

    print(f"\n📊 20 nhãn ÍT nhất:")
    for cid, cnt in sorted_cats[:20]:
        max_s = cat_max_map.get(cid, 15_000)
        flag  = "⚠️ " if cnt < MIN_SAMPLES_TARGET else "  "
        pct   = 100 * cnt // max_s
        print(f"  {flag}{cnt:>7,}/{max_s:<6,} ({pct:>3}%)  {cat_name_map.get(cid, cid)}")

    print(f"\n📊 20 nhãn NHIỀU nhất:")
    for cid, cnt in reversed(sorted_cats[-20:]):
        max_s = cat_max_map.get(cid, 15_000)
        pct   = 100 * cnt // max_s
        print(f"       {cnt:>7,}/{max_s:<6,} ({pct:>3}%)  {cat_name_map.get(cid, cid)}")

    # Nhãn vẫn 0
    all_ids = {cat['id'] for cat in categories}
    missing = all_ids - set(per_cat_count.keys())
    if missing:
        print(f"\n❌ Nhãn 0 mẫu ({len(missing)}) — cần thêm synonyms:")
        for cid in sorted(missing):
            print(f"   ✗ {cat_name_map.get(cid, cid)}")
    else:
        print(f"\n✅ Tất cả {len(categories)} nhãn đều có dữ liệu!")

    # Imbalance
    counts = list(per_cat_count.values())
    if counts:
        ratio = max(counts) / max(min(counts), 1)
        below = sum(1 for c in counts if c < MIN_SAMPLES_TARGET)
        print(f"\n   Imbalance ratio    : {ratio:.1f}x")
        print(f"   Nhãn < {MIN_SAMPLES_TARGET} mẫu   : {below}/{len(categories)}")
        if ratio > 30:
            print("   ⚠️  Còn mất cân bằng — bật class_weights trong train_model.py")
        else:
            print("   ✅ Imbalance chấp nhận được")


if __name__ == "__main__":
    generate()