from app.ingestion.image_processor import extract_text_from_image


pages = extract_text_from_image(
    "test_data/test_image1.jpeg"
)

print("\n--- EXTRACTED PAGES ---\n")

for page in pages:
    print(f"Page {page['page']}:")
    print(page["text"])