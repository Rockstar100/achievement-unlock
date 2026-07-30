import pandas as pd

df = pd.read_csv("data/gold/gold_dim_trending_pet_products.csv")
print("rows", len(df))
print("dup product_id", df["product_id"].duplicated().sum())
print("dup title", df["canonical_title"].str.lower().duplicated().sum())
print("categories", df["category"].value_counts().to_dict())
print("brands", df["normalized_brand"].value_counts().head(12).to_dict())
print("sources sample", df["sources"].head(5).tolist())
if "image_url" in df.columns:
    has_img = df["image_url"].fillna("").astype(str).str.startswith("http").sum()
    print("products_with_image", has_img, "/", len(df))
    print("image sample", df.loc[df["image_url"].fillna("").astype(str).str.startswith("http"), "image_url"].head(3).tolist())
bad = ["cattle", "poultry", "guinea", "aquarium", "pebble", "vase filler", "livestock",
       "liniment", "papad", "pain killer", "kottakkal", "drying cloth"]
for b in bad:
    n = df["canonical_title"].str.lower().str.contains(b, na=False).sum()
    if n:
        print("bad", b, n)
print("top 10:")
for _, r in df.head(10).iterrows():
    print(f"  {r['trend_score']:.1f} [{r['category']}] {str(r['canonical_title'])[:70]}")
print("erina rows", df["canonical_title"].str.contains("Erina", case=False, na=False).sum())
