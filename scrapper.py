import os
import csv
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re

# Configuration
PAGES_TO_SCRAPE = 50
PAGES_FOLDER = "target_pages"
OUTPUT_CSV = "target_products.csv"

# Create folders if they don't exist
os.makedirs(PAGES_FOLDER, exist_ok=True)

def extract_star_rating(container):
    if not container:
        return "N/A"
    rating_elem = container.select_one('[aria-label*="out of 5 stars"]')
    if rating_elem and rating_elem.has_attr('aria-label'):
        match = re.search(r'(\d+(?:\.\d+)?)\s*out\s*of\s*5', rating_elem['aria-label'])
        if match:
            return f"{float(match.group(1))}/5"
    stars_container = container.select_one('div[data-test="rating-stars"]')
    if stars_container:
        filled_stars = len(stars_container.select('svg[data-test*="full-star"]'))
        half_star = 1 if stars_container.select('svg[data-test*="half-star"]') else 0
        return f"{filled_stars + half_star*0.5}/5"
    text_elem = container.find(string=re.compile(r'out of 5'))
    if text_elem:
        match = re.search(r'(\d+(?:\.\d+)?)\s*out\s*of\s*5', text_elem)
        if match:
            return f"{float(match.group(1))}/5"
    return "N/A"

def extract_review_count(container):
    if not container:
        return "0"
    reviews_elem = container.select_one('[data-test="rating-count"]')
    if reviews_elem:
        review_text = reviews_elem.get_text(strip=True)
        match = re.search(r'(\d+)', review_text.replace(",", ""))
        return match.group(1) if match else "0"
    text_elem = container.find(string=re.compile(r'review|rating'))
    if text_elem:
        match = re.search(r'(\d+)', text_elem.replace(",", ""))
        return match.group(1) if match else "0"
    return "0"

def extract_inventory_count(container):
    if not container:
        return "N/A"
    inventory_elem = container.find(string=re.compile(r'only \d+ left|\d+ left|only \d+ in stock|low stock', re.IGNORECASE))
    if inventory_elem:
        match = re.search(r'(\d+)', inventory_elem)
        return match.group(1) if match else "Low Stock"
    return "N/A"

def is_sold_by_target(container):
    if not container:
        return "No"
    only_at_target = container.find(string=re.compile(r'only at target', re.IGNORECASE))
    if only_at_target:
        return "Yes"
    target_logo = container.select_one('svg[aria-label="Target logo"]')
    if target_logo:
        return "Yes"
    sold_by = container.find(string=re.compile(r'sold by target', re.IGNORECASE))
    if sold_by:
        return "Yes"
    return "No"

def extract_product_data(soup):
    base_url = "https://www.target.com"
    products = []
    seen_urls = set()

    product_containers = soup.select('div[data-test*="product-card"], div[data-test*="@web/ProductCard"]')

    for container in product_containers:
        product = {}

        link = container.select_one('a[href*="/p/"][data-test="product-title"]')
        if not link or not link.has_attr('href'):
            continue

        raw_url = urljoin(base_url, link['href'])
        parsed = urlparse(raw_url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean_url in seen_urls:
            continue
        seen_urls.add(clean_url)
        product['url'] = clean_url

        product['title'] = link.get_text(strip=True)
        if not product['title']:
            continue

        brand_elem = container.select_one('[data-test*="brand"]')
        product['brand'] = brand_elem.get_text(strip=True) if brand_elem else "N/A"

        price_elem = container.select_one('[data-test="current-price"]')
        if not price_elem:
            continue
        product['price'] = price_elem.get_text(strip=True)

        product['rating'] = extract_star_rating(container)
        product['reviews'] = extract_review_count(container)
        product['inventory'] = extract_inventory_count(container)

        sold_by = is_sold_by_target(container)
        product['sold_by_target'] = sold_by
        product['seller_name'] = "Target" if sold_by == "Yes" else "N/A"

        tcin_match = re.search(r'/A-(\d+)', clean_url)
        product['tcin'] = tcin_match.group(1) if tcin_match else "N/A"

        products.append(product)

    return products

def load_existing_products():
    """Load existing products from CSV to avoid duplicates"""
    existing_products = set()
    if os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, mode='r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_products.add(row['url'])
    return existing_products

def scrape_all_pages():
    existing_urls = load_existing_products()
    all_products = []
    new_products_count = 0

    for page_num in range(1, PAGES_TO_SCRAPE + 1):
        filename = os.path.join(PAGES_FOLDER, f"Action Figures _ Page {page_num} _ Target.html")
        
        if not os.path.exists(filename):
            print(f"⚠️ File not found: {filename} - skipping")
            continue

        try:
            with open(filename, "r", encoding="utf-8", errors="ignore") as f:
                html = f.read()
            soup = BeautifulSoup(html, "html.parser")
            products = extract_product_data(soup)
            
            # Filter out existing products
            new_products = [p for p in products if p['url'] not in existing_urls]
            all_products.extend(new_products)
            new_products_count += len(new_products)
            
            # Add new URLs to the existing set to avoid duplicates in this run
            existing_urls.update(p['url'] for p in new_products)
            
            print(f"✅ Processed page {page_num}: Found {len(products)} products ({len(new_products)} new)")

        except Exception as e:
            print(f"❌ Error processing page {page_num}: {str(e)}")
            continue

    return all_products, new_products_count

def save_to_csv(products):
    if not products:
        print("No new products to save.")
        return

    file_exists = os.path.exists(OUTPUT_CSV)
    fieldnames = ['url', 'title', 'brand', 'price', 'rating', 'reviews', 
                 'inventory', 'sold_by_target', 'seller_name', 'tcin']

    with open(OUTPUT_CSV, mode='a' if file_exists else 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(products)

def main():
    print(f"Starting scrape of up to {PAGES_TO_SCRAPE} pages...")
    products, new_count = scrape_all_pages()
    
    if new_count > 0:
        save_to_csv(products)
        print(f"\nSuccessfully added {new_count} new products to {OUTPUT_CSV}")
        
        # Print sample output
        print("\nSample products:")
        for i, product in enumerate(products[:2]):
            print(f"\nProduct {i+1}:")
            for key, value in product.items():
                print(f"{key.capitalize().replace('_', ' ')}: {value}")
            print("-" * 50)
    else:
        print("\nNo new products found to add.")

    # Show total in CSV
    if os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, mode='r', encoding='utf-8') as f:
            total = sum(1 for _ in csv.DictReader(f)) - 1  # Subtract header
        print(f"\nTotal products in {OUTPUT_CSV}: {total}")

if __name__ == "__main__":
    main()