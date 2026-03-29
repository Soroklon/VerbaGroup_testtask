from pathlib import Path

from exporter import save_xlsx
from wb_parser import parse


def read_config(path="config.txt"):
    config = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and "=" in line:
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip()
    return config


def main():
    config = read_config()

    query = config["query"]
    limit = int(config["limit"])
    min_rating = float(config["min_rating"])
    max_price = int(config["max_price"])
    country = config["country"].lower()

    products = parse(query, limit)

    result_dir = Path("result")
    result_dir.mkdir(exist_ok=True)

    save_xlsx(products, result_dir / "catalog.xlsx")

    filtered = [
        p for p in products
        if p["rating"] >= min_rating
        and p["price"] <= max_price
        and country in p["country"].lower()
    ]
    save_xlsx(filtered, result_dir / "filtered.xlsx")

    print(f"\nГотово. Отфильтровано: {len(filtered)} из {len(products)}")


if __name__ == "__main__":
    main()
