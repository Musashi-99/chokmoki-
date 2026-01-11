from typing import Dict, Any
from src.cqrs.queries import (
    ProductListQuery,
    ProductGetQuery,
    ProductSearchQuery,
    ProductGetByIdsQuery,
    CategoryListQuery,
    CategoryGetQuery,
    OrderListQuery,
    OrderGetQuery
)
from src.cqrs.mutations import (
    ProductCreateMutation,
    ProductUpdateMutation,
    ProductDeleteMutation,
    CategoryCreateMutation,
    CategoryUpdateMutation,
    CategoryDeleteMutation,
    OrderCreateMutation,
    OrderStatusUpdateMutation,
    ContactCreateMutation
)


class CQRSRouter:
    QUERIES: Dict[str, Any] = {
        "product.list": ProductListQuery,
        "product.get": ProductGetQuery,
        "product.search": ProductSearchQuery,
        "product.getByIds": ProductGetByIdsQuery,
        "category.list": CategoryListQuery,
        "category.get": CategoryGetQuery,
        "order.list": OrderListQuery,
        "order.get": OrderGetQuery,
    }
    
    MUTATIONS: Dict[str, Any] = {
        "product.create": ProductCreateMutation,
        "product.update": ProductUpdateMutation,
        "product.delete": ProductDeleteMutation,
        "category.create": CategoryCreateMutation,
        "category.update": CategoryUpdateMutation,
        "category.delete": CategoryDeleteMutation,
        "order.create": OrderCreateMutation,
        "order.updateStatus": OrderStatusUpdateMutation,
        "contact.create": ContactCreateMutation,
    }
    
    @classmethod
    async def execute_query(cls, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if operation not in cls.QUERIES:
            raise ValueError(f"Unknown query operation: {operation}")
        
        query_class = cls.QUERIES[operation]
        query = query_class()
        return await query.execute(params)
    
    @classmethod
    async def execute_mutation(cls, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if operation not in cls.MUTATIONS:
            raise ValueError(f"Unknown mutation operation: {operation}")
        
        mutation_class = cls.MUTATIONS[operation]
        mutation = mutation_class()
        return await mutation.execute(params)

