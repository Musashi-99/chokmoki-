from typing import Dict, Any
from src.cqrs.base import CommandMutation
from src.services.newsletter_service import NewsletterService
from src.models.newsletter import NewsletterCreate
from src.models.common import MutationResponseDTO


class NewsletterSubscribeMutation(CommandMutation):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = NewsletterService()
        email = params.get("email")
        
        if not email:
            raise ValueError("Email is required")
        
        try:
            # Check if email already exists
            if await service.exists(email):
                return MutationResponseDTO(
                    success=False,
                    message="Email already exists"
                ).model_dump()
            
            newsletter_data = NewsletterCreate(email=email)
            newsletter = await service.create(newsletter_data)
            return MutationResponseDTO(
                success=True,
                data=newsletter.model_dump(by_alias=True),
                message="Successfully subscribed to newsletter"
            ).model_dump()
        except ValueError as e:
            return MutationResponseDTO(
                success=False,
                message=str(e)
            ).model_dump()
