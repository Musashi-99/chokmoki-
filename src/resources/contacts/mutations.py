from typing import Dict, Any
from src.cqrs.base import CommandMutation
from src.services.contact_service import ContactService
from src.models.contact import ContactCreate
from src.models.common import MutationResponseDTO


class ContactCreateMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = ContactService()
        contact_data = ContactCreate(**params)
        contact = await service.create(contact_data)
        return MutationResponseDTO(data=contact.model_dump(by_alias=True)).model_dump()
