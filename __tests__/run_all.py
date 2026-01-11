import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.connection import db
import importlib.util


async def run_test_file(file_path):
    spec = importlib.util.spec_from_file_location("test_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    if hasattr(module, 'test_create_categories'):
        await module.test_create_categories()
    if hasattr(module, 'test_create_products'):
        await module.test_create_products()
    if hasattr(module, 'test_list_products_with_categories'):
        await module.test_list_products_with_categories()
    if hasattr(module, 'test_search_products'):
        await module.test_search_products()
    if hasattr(module, 'test_update_category_and_verify_products'):
        await module.test_update_category_and_verify_products()


async def main():
    await db.connect()
    
    test_files = [
        "__tests__/1__categories.test.py",
        "__tests__/2__product.test.py",
        "__tests__/3__category_update.test.py"
    ]
    
    for test_file in test_files:
        file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), test_file)
        if os.path.exists(file_path):
            print(f"\n{'='*50}")
            print(f"Running {test_file}")
            print(f"{'='*50}")
            await run_test_file(file_path)
        else:
            print(f"File not found: {test_file}")


if __name__ == "__main__":
    asyncio.run(main())

