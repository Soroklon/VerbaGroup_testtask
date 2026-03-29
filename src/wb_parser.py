import time
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v4/search"


def _request(url, params=None):
    for attempt in range(6):
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if r.status_code == 429:
            wait = 10 * (attempt + 1)
            print(f"  429 - пауза {wait} секунд...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()


_BASKET_ANCHORS = [
    (143, 1), (287, 2), (431, 3), (719, 4),
    (1007, 5), (1061, 6), (1115, 7), (1169, 8),
    (1313, 9), (1601, 10), (1655, 11), (1919, 12),
    (2045, 13), (2189, 14), (2405, 15), (2621, 16),
    (2837, 17), (3049, 18), (3054, 19), (4123, 23),
    (4811, 26), (5071, 27), (5234, 28), (7493, 35), (7714, 36),
]

_basket_cache: dict[int, str] = {}


def _start_basket(vol):
    result = 1
    for limit, num in _BASKET_ANCHORS:
        if vol >= limit:
            result = num
        else:
            break
    return result


def _resolve_basket(nm_id):
    vol = nm_id // 100000
    if vol in _basket_cache:
        return _basket_cache[vol]

    part = nm_id // 1000
    for num in range(_start_basket(vol), 100):
        basket = f"{num:02d}"
        url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 429:
            time.sleep(30)
            r = requests.get(url, headers=HEADERS, timeout=10)
        time.sleep(0.5)
        if r.status_code == 200:
            _basket_cache[vol] = basket
            return basket

    raise requests.HTTPError(f"Корзина не найдена для артикула {nm_id}")


def _build_image_urls(nm_id, pics):
    basket = _basket_cache.get(nm_id // 100000, "01")
    vol = nm_id // 100000
    part = nm_id // 1000
    base = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/images/big"
    return [f"{base}/{i}.jpg" for i in range(1, min(pics, 10) + 1)]


def _fetch_card_json(nm_id):
    vol = nm_id // 100000
    part = nm_id // 1000
    basket = _resolve_basket(nm_id)
    url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
    return _request(url).json()


def _search_pages(query, limit):
    products = []
    page = 1
    while True:
        params = {
            "appType": 1,
            "curr": "rub",
            "dest": -1257786,
            "query": query,
            "resultset": "catalog",
            "sort": "popular",
            "spp": 30,
            "page": page,
        }
        try:
            page_products = _request(SEARCH_URL, params).json().get("products", [])
        except requests.RequestException:
            print(f"  Лимит запросов достигнут на странице {page}, сохраняю {len(products)} товаров...")
            break
        if not page_products:
            break
        products.extend(page_products)
        print(f"  страница {page}: +{len(page_products)} товаров (всего {len(products)})")
        if limit and len(products) >= limit:
            break
        page += 1
        time.sleep(2)
    return products[:limit] if limit else products


def _format_characteristics(card_json):
    groups = card_json.get("grouped_options", [])
    if groups:
        lines = []
        for group in groups:
            lines.append(f"[{group['group_name']}]")
            for opt in group.get("options", []):
                lines.append(f"  {opt['name']}: {opt['value']}")
        return "\n".join(lines)
    options = card_json.get("options", [])
    return "\n".join(f"{o['name']}: {o['value']}" for o in options)


def _find_characteristic(card_json, name):
    for group in card_json.get("grouped_options", []):
        for opt in group.get("options", []):
            if name.lower() in opt["name"].lower():
                return opt["value"]
    for opt in card_json.get("options", []):
        if name.lower() in opt["name"].lower():
            return opt["value"]
    return ""


def _get_price(raw):
    for size in raw.get("sizes", []):
        price = size.get("price", {}).get("product")
        if price:
            return price // 100
    return 0


def _build_product(raw, card_json):
    nm_id = raw["id"]
    sizes = raw.get("sizes", [])
    size_names = [s.get("origName") or s.get("name", "") for s in sizes if s.get("origName") or s.get("name")]
    supplier_id = raw.get("supplierId")

    return {
        "url": f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx",
        "article": nm_id,
        "name": raw.get("name", ""),
        "price": _get_price(raw),
        "description": card_json.get("description", ""),
        "images": ", ".join(_build_image_urls(nm_id, raw.get("pics", 1))),
        "characteristics": _format_characteristics(card_json),
        "seller_name": raw.get("supplier", ""),
        "seller_url": f"https://www.wildberries.ru/seller/{supplier_id}" if supplier_id else "",
        "sizes": ", ".join(size_names),
        "stock": raw.get("totalQuantity", 0),
        "rating": raw.get("reviewRating", 0),
        "reviews": raw.get("feedbacks", 0),
        "country": _find_characteristic(card_json, "страна"),
    }


def _warmup():
    try:
        requests.get("https://www.wildberries.ru/", timeout=10)
        time.sleep(1)
    except requests.RequestException:
        pass


def parse(query, limit):
    print(f"Поиск: {query!r}, лимит: {'все товары' if not limit else limit}")
    _warmup()
    raw_products = _search_pages(query, limit)
    print(f"Найдено: {len(raw_products)} товаров. Запрос деталей:")

    products = []
    for i, raw in enumerate(raw_products, 1):
        try:
            card_json = _fetch_card_json(raw["id"])
        except requests.RequestException:
            print(f"  Лимит запросов достигнут на [{i}/{len(raw_products)}], сохраняю {len(products)} товаров...")
            break
        products.append(_build_product(raw, card_json))
        print(f"  [{i}/{len(raw_products)}] {raw['id']} - {raw.get('name', '')[:50]}")
        time.sleep(1)

    return products
