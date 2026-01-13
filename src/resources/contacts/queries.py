from typing import Dict, Any
from src.cqrs.base import CommandQuery
from src.services.contact_service import ContactService
from src.models.common import ListResponseDTO


class ContactListQuery(CommandQuery):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ContactService()
        skip = params.get("skip", 0)
        limit = params.get("take") or params.get("limit", 20)
        
        contacts = await service.list(skip=skip, limit=limit)
        total = await service.count()
        
        return ListResponseDTO(
            data=[contact.model_dump(by_alias=True) for contact in contacts],
            count=total
        ).model_dump()
