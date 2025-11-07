# import os
# from src.extractor import extract_work_order_details
# from src.db import init_db, insert_or_update_prompt

# def main():
#     input_dir = "input"
#     output_dir = "output"

#     print("=== Gemini Work Order Extraction ===\n")

#     # Initialize database and insert default prompt if needed
#     init_db()
#     default_prompt = """Extract key work or purchase order details in JSON format:
#     {
#         "document_type": "",
#         "order_number": "",
#         "project_name": "",
#         "site_name": "",
#         "start_date": "",
#         "end_date": "",
#         "tasks": [
#             {"description": "", "quantity": "", "unit": "", "assigned_to": ""}
#         ],
#         "status": ""
#     }"""
#     insert_or_update_prompt("work_order_extraction", default_prompt)

#     # Loop through all PDF files in the input folder
#     for filename in os.listdir(input_dir):
#         if filename.lower().endswith(".pdf"):
#             file_path = os.path.join(input_dir, filename)
#             print(f"[PROCESSING] {filename}")
#             try:
#                 extract_work_order_details(file_path, output_dir)
#             except Exception as e:
#                 print(f"[ERROR] Failed to process {filename}: {e}")
#         else:
#             print(f"[SKIPPED] {filename} is not a PDF file")

#     print("\n[COMPLETE] Processed all available files.")

# if __name__ == "__main__":
#     main()


import os
from src.extractor import extract_work_order_details
from src.db import init_db, insert_or_update_prompt

def main():
    input_dir = "input"
    output_dir = "output"

    print("=== Gemini Work Order Extraction ===\n")

    # Initialize database and insert default prompt
    init_db()
    default_prompt = """Extract key work or purchase order details in JSON format:
    {
        "document_type": "",
        "order_number": "",
        "project_name": "",
        "site_name": "",
        "start_date": "",
        "end_date": "",
        "tasks": [
            {"description": "", "quantity": "", "unit": "", "assigned_to": ""}
        ],
        "status": ""
    }"""
    insert_or_update_prompt("work_order_extraction", default_prompt)

    # Loop through all PDF files in input folder (recursively)
    for root, _, files in os.walk(input_dir):
        for filename in files:
            if filename.lower().endswith(".pdf"):
                file_path = os.path.join(root, filename)
                print(f"[PROCESSING] {filename}")
                try:
                    extract_work_order_details(file_path, output_dir)
                except Exception as e:
                    print(f"[ERROR] Failed to process {filename}: {e}")
            else:
                print(f"[SKIPPED] {filename} is not a PDF file")

    print("\n[COMPLETE] Processed all available files.")

if __name__ == "__main__":
    main()
