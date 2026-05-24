from typing import List, Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from src.models.product import PyObjectId


class SocialGridLink(BaseModel):
    platform: str = ""
    handle: str = ""
    image_url: str = ""
    url: str = ""


class HomePageSettings(BaseModel):
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    settings_key: str = "main"
    heritage_eyebrow: str = ""
    heritage_title_line1: str = ""
    heritage_title_line2: str = ""
    heritage_body: str = ""
    heritage_cta_label: str = ""
    categories_eyebrow: str = ""
    categories_title: str = ""
    categories_intro: str = ""
    best_sellers_eyebrow: str = ""
    best_sellers_title: str = ""
    curated_eyebrow: str = ""
    curated_title: str = ""
    curated_description: str = ""
    social_eyebrow: str = ""
    social_title: str = ""
    social_body: str = ""
    social_instagram_image_url: str = ""
    social_facebook_image_url: str = ""
    postcard_title: str = ""
    postcard_body: str = ""
    postcard_button_label: str = ""
    newsletter_heading: str = ""
    newsletter_body: str = ""
    trust_eyebrow: str = ""
    trust_title: str = ""
    trust_card_1_title: str = ""
    trust_card_1_description: str = ""
    trust_card_2_title: str = ""
    trust_card_2_description: str = ""
    trust_card_3_title: str = ""
    trust_card_3_description: str = ""
    trust_card_4_title: str = ""
    trust_card_4_description: str = ""
    testimonials_eyebrow: str = ""
    testimonials_title: str = ""
    footer_tagline: str = ""
    footer_explore_heading: str = ""
    footer_shop_heading: str = ""
    footer_newsletter_heading: str = ""
    footer_copyright_text: str = ""
    footer_craft_text: str = ""
    categories_all_title: str = ""
    categories_all_microcopy: str = ""
    categories_all_image_url: str = ""
    categories_all_to: str = "/products"
    categories_card_cta: str = ""
    categories_view_all_label: str = ""
    faq_eyebrow: str = ""
    faq_title: str = ""
    faq_cta_label: str = ""
    social_instagram_handle: str = ""
    social_facebook_handle: str = ""
    social_links: List[SocialGridLink] = Field(default_factory=list)
    active: bool = True
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class HomePageSettingsUpdate(BaseModel):
    heritage_eyebrow: Optional[str] = None
    heritage_title_line1: Optional[str] = None
    heritage_title_line2: Optional[str] = None
    heritage_body: Optional[str] = None
    heritage_cta_label: Optional[str] = None
    categories_eyebrow: Optional[str] = None
    categories_title: Optional[str] = None
    categories_intro: Optional[str] = None
    best_sellers_eyebrow: Optional[str] = None
    best_sellers_title: Optional[str] = None
    curated_eyebrow: Optional[str] = None
    curated_title: Optional[str] = None
    curated_description: Optional[str] = None
    social_eyebrow: Optional[str] = None
    social_title: Optional[str] = None
    social_body: Optional[str] = None
    social_instagram_image_url: Optional[str] = None
    social_facebook_image_url: Optional[str] = None
    postcard_title: Optional[str] = None
    postcard_body: Optional[str] = None
    postcard_button_label: Optional[str] = None
    newsletter_heading: Optional[str] = None
    newsletter_body: Optional[str] = None
    trust_eyebrow: Optional[str] = None
    trust_title: Optional[str] = None
    trust_card_1_title: Optional[str] = None
    trust_card_1_description: Optional[str] = None
    trust_card_2_title: Optional[str] = None
    trust_card_2_description: Optional[str] = None
    trust_card_3_title: Optional[str] = None
    trust_card_3_description: Optional[str] = None
    trust_card_4_title: Optional[str] = None
    trust_card_4_description: Optional[str] = None
    testimonials_eyebrow: Optional[str] = None
    testimonials_title: Optional[str] = None
    footer_tagline: Optional[str] = None
    footer_explore_heading: Optional[str] = None
    footer_shop_heading: Optional[str] = None
    footer_newsletter_heading: Optional[str] = None
    footer_copyright_text: Optional[str] = None
    footer_craft_text: Optional[str] = None
    categories_all_title: Optional[str] = None
    categories_all_microcopy: Optional[str] = None
    categories_all_image_url: Optional[str] = None
    categories_all_to: Optional[str] = None
    categories_card_cta: Optional[str] = None
    categories_view_all_label: Optional[str] = None
    faq_eyebrow: Optional[str] = None
    faq_title: Optional[str] = None
    faq_cta_label: Optional[str] = None
    social_instagram_handle: Optional[str] = None
    social_facebook_handle: Optional[str] = None
    social_links: Optional[List[SocialGridLink]] = None
    active: Optional[bool] = None
